import React, { useState, useEffect } from 'react';
import { useSignAndExecuteTransaction } from '@mysten/dapp-kit';
import { Transaction } from '@mysten/sui/transactions';
import './Pools.css';

function Pools({ walletAddress, onSelectPool, onBack }) {
  const { mutate: signAndExecuteTransaction } = useSignAndExecuteTransaction();
  const [pools, setPools] = useState([]);
  const [loading, setLoading] = useState(true);
  const [joining, setJoining] = useState(null);

  useEffect(() => {
    fetchPools();
  }, []);

  const fetchPools = async () => {
    try {
      const apiUrl = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';
      const response = await fetch(`${apiUrl}/pools`);
      const data = await response.json();
      setPools(data.pools || []);
    } catch (error) {
      console.error('Error fetching pools:', error);
      setPools([]); // Clear pools on error instead of showing mock data
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
      const entryFee = pool.entry_fee || "0.1";
      const entryFeeMist = parseFloat(entryFee) * 1_000_000_000;
      const poolObjectId = pool.contract_id || "0x0";  // Smart contract pool object ID
      const apiUrl = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';
      const packageId = import.meta.env.VITE_SUI_PACKAGE_ID || "0x0";

      const txb = new Transaction();
      txb.moveCall({
        target: `${packageId}::pool::join_pool`,
        arguments: [
          txb.object(poolObjectId),
          txb.pure.u64(entryFeeMist),
          txb.pure.address(walletAddress)
        ]
      });

      const result = await signAndExecuteTransaction({
        transaction: txb,
      });

      console.log('Transaction result:', result);

      // Notify backend about the join (for tracking only)
      const response = await fetch(`${apiUrl}/join-pool`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          pool_id: pool.id,
          wallet_address: walletAddress,
          transaction_id: result.digest,
          amount: entryFeeMist,
        }),
      });

      const data = await response.json();
      console.log('Join pool response:', data);

      if (data.status === 'success') {
        onSelectPool(pool);
      } else {
        alert('Failed to join pool: ' + data.message);
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
        <h2 className="pools-title">Competition Pools</h2>
        <p>Loading pools...</p>
      </div>
    );
  }

  return (
    <div className="pools-container">
      <button className="back-btn" onClick={onBack}>← Back</button>
      <h2 className="pools-title">Competition Pools</h2>
      <div className="pools-grid">
        {pools.map(pool => (
          <div key={pool.id} className="pool-card">
            <h3 className="pool-name">{pool.name}</h3>
            <div className="pool-info">
              <p>⏱️ Duration: {pool.duration}</p>
              <p>💰 Entry Fee: {pool.entry_fee}</p>
              <p>🏆 Prize Pool: {pool.prize}</p>
              <p>👥 Players: {pool.players}</p>
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
