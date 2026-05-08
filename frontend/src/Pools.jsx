import React, { useState, useEffect, useMemo } from 'react';
import { useSignAndExecuteTransaction } from '@mysten/dapp-kit';
import { Transaction } from '@mysten/sui/transactions';
import './Pools.css';

const DEV_FEE_PERCENT = 2.5;

function Pools({ walletAddress, onSelectPool, onBack }) {
  const { mutateAsync: signAndExecuteTransaction } = useSignAndExecuteTransaction();
  const [pools, setPools] = useState([]);
  const [loading, setLoading] = useState(true);
  const [joining, setJoining] = useState(null);
  const [nowTs, setNowTs] = useState(() => Date.now());

  useEffect(() => {
    fetchPools();
  }, []);

  useEffect(() => {
    const timer = setInterval(() => {
      setNowTs(Date.now());
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  const formatCountdown = (seconds) => {
    if (seconds == null) return null;
    const rem = Math.max(0, seconds);
    const days = Math.floor(rem / 86400);
    const hours = Math.floor((rem % 86400) / 3600);
    const minutes = Math.floor((rem % 3600) / 60);
    const secs = rem % 60;
    const parts = [];
    if (days > 0) parts.push(`${days}d`);
    parts.push(String(hours).padStart(2, '0') + ':' + String(minutes).padStart(2, '0') + ':' + String(secs).padStart(2, '0'));
    return parts.join(' ');
  };

  const poolsWithCountdown = useMemo(() => {
    return pools.map((pool) => {
      const endsAtSeconds = typeof pool.ends_at === 'number' ? pool.ends_at : null;
      const serverRemaining = typeof pool.seconds_remaining === 'number' ? pool.seconds_remaining : null;
      const liveRemaining = endsAtSeconds
        ? Math.max(0, Math.floor(endsAtSeconds - nowTs / 1000))
        : (serverRemaining != null ? Math.max(0, serverRemaining - Math.floor(nowTs / 1000)) : null);
      return {
        ...pool,
        _endsAtSeconds: endsAtSeconds,
        _secondsRemainingLive: liveRemaining,
      };
    });
  }, [pools, nowTs]);

  const fetchPools = async () => {
    try {
      let rawApiUrl = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';
      console.log('Original VITE_API_URL:', rawApiUrl);
      
      // 1. Remove ANY leading/trailing whitespace or quotes
      let apiUrl = rawApiUrl.trim().replace(/^["']|["']$/g, '');
      
      // 2. If it contains the current domain, it's definitely wrong
      if (apiUrl.includes(window.location.origin)) {
        apiUrl = apiUrl.replace(window.location.origin, '');
      }

      // 3. Ensure it starts with http
      if (apiUrl && !apiUrl.startsWith('http')) {
        // If it starts with a slash, remove it
        apiUrl = apiUrl.replace(/^\/+/, '');
        apiUrl = `https://${apiUrl}`;
      }
      
      // 4. Final slash cleanup
      apiUrl = apiUrl.replace(/\/+$/, '');
      
      const finalUrl = `${apiUrl}/pools`;
      console.log('FINAL FETCH URL:', finalUrl);

      const response = await fetch(finalUrl);
      
      if (!response.ok) {
        console.error(`Backend returned ${response.status} for ${finalUrl}`);
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      
      const data = await response.json();
      console.log('Successfully fetched pools:', data);
      setPools(data.pools || []);
    } catch (error) {
      console.error('FETCH ERROR:', error);
      setPools([]); 
    } finally {
      setLoading(false);
    }
  };

  const handleJoinPool = async (pool) => {
    if (!walletAddress) {
      alert('Please connect your wallet to join a pool');
      return;
    }

    try {
      const poolObjectId = pool.contract_id;
      console.log(`Checking pool initialization for ${pool.name}:`, poolObjectId);
      
      if (!poolObjectId || poolObjectId === "0x0" || poolObjectId === "undefined") {
        console.error('Pool missing or invalid contract_id:', pool);
        alert(`This pool (${pool.name}) has not been initialized on the blockchain yet (ID: ${poolObjectId}). Please check your Render environment variables.`);
        return;
      }

      const entryFee = pool.entry_fee || "0.1";
      const entryFeeMist = parseFloat(entryFee) * 1_000_000_000;
      console.log('Entry fee raw:', pool.entry_fee, 'parsed:', entryFee, 'mist:', entryFeeMist);
      let apiUrl = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';
      apiUrl = apiUrl.replace(/\/$/, '');
      const packageId = import.meta.env.VITE_SUI_PACKAGE_ID || "0x0";
      const devWallet = import.meta.env.VITE_DEV_WALLET || "0x0d32cdae7aa9a25003687dcbfe154c5d13bc51b76fd29116a54276c1f80fd140";

      const txb = new Transaction();

      // 1. Split the entry fee from gas
      const [feeCoin] = txb.splitCoins(txb.gas, [txb.pure.u64(entryFeeMist)]);

      // 2. Deposit fee into pool escrow AND register player in one call
      txb.moveCall({
        target: `${packageId}::pool::deposit_and_join`,
        arguments: [
          txb.pure.id(poolObjectId),
          feeCoin,
          txb.pure.address(walletAddress)
        ]
      });

      console.log('Executing transaction...');
      const result = await signAndExecuteTransaction({
        transaction: txb,
      });

      console.log('Transaction executed. Result:', result);

      if (!result) {
        throw new Error('Transaction result is undefined');
      }

      if (!result.digest) {
        console.error('Full result object:', JSON.stringify(result));
        throw new Error('Transaction result missing digest');
      }

      // Notify backend about the join (for tracking only)
      const response = await fetch(`${apiUrl}/join-pool`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          pool_id: pool.id,
          wallet: walletAddress,
          transaction_id: result.digest,
          amount: String(entryFeeMist),
        }),
      });

      const data = await response.json();
      console.log('Join pool response:', data);

      if (data.status === 'success' || data.detail === 'Already joined this pool') {
        onSelectPool(pool);
      } else {
        alert('Failed to join pool: ' + (data.message || data.detail || 'Unknown error'));
      }
    } catch (error) {
      console.error('Error joining pool:', error);
      alert('Failed to join pool. Please try again.');
    } finally {
      setJoining(null);
    }
  };

  if (loading) {
    return (
      <div className="pools-container">
        <button className="back-btn" onClick={onBack}>← Back</button>
        <h2 className="pools-title">Competition Pools v2</h2>
        <p>Loading pools...</p>
      </div>
    );
  }

  return (
    <div className="pools-container">
      <button className="back-btn" onClick={onBack}>← Back</button>
      <h2 className="pools-title">Competition Pools v2</h2>
      <p className="dev-fee-note">
        Note: A {DEV_FEE_PERCENT}% dev fee (paid in SUI) is deducted from every pool before SUITRUMP rewards are distributed.
      </p>
      <div className="pools-grid">
        {poolsWithCountdown.map(pool => (
          <div key={pool.id} className="pool-card">
            <h3 className="pool-name">{pool.name}</h3>
            <div className="pool-info">
              <p>⏱️ Duration: {pool.duration}</p>
              {pool._secondsRemainingLive != null && (
                <p className="pool-countdown">
                  🕒 Time remaining: {formatCountdown(pool._secondsRemainingLive)}
                </p>
              )}
              <p>💰 Entry Fee: {pool.entry_fee}</p>
              <p>🏆 Prize Pool: {pool.prize}</p>
              <p>👥 Players: {pool.players}</p>
              {Array.isArray(pool.payout_structure) && pool.payout_structure.length > 0 && (
                <div className="pool-payouts">
                  <p>🏅 Payouts (after dev fee):</p>
                  <ul>
                    {pool.payout_structure.map((pct, idx) => (
                      <li key={idx}>
                        {idx + 1}{['st','nd','rd'][idx] || 'th'} place: {pct}%
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {(() => {
                const prizeValue = parseFloat(pool.prize);
                if (Number.isNaN(prizeValue)) return null;
                const netPrize = prizeValue * ((100 - DEV_FEE_PERCENT) / 100);
                return (
                  <p className="dev-fee-inline">
                    After dev fee ({DEV_FEE_PERCENT}%): {netPrize.toFixed(3)} SUITRUMP
                  </p>
                );
              })()}
            </div>
            <button 
              className="join-btn"
              onClick={() => handleJoinPool(pool)}
              disabled={joining === pool.id}
            >
              {joining === pool.id ? 'Joining...' : 'Join Pool'}
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}

export default Pools;
