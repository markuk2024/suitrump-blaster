import React, { useState, useEffect } from 'react';
import './Leaderboard.css';

function Leaderboard({ onBack, walletAddress }) {
  const [leaderboard, setLeaderboard] = useState([]);
  const [loading, setLoading] = useState(true);
  const [pools, setPools] = useState({});
  const [selectedPayoutPool, setSelectedPayoutPool] = useState('daily');
  const [payoutStatus, setPayoutStatus] = useState(null);

  const DEV_WALLET = "0x4c2891f70f1317fed1198140e0f06f49593c82558b2b467e1717c23fee9131a6";
  const isAdmin = walletAddress && walletAddress.toLowerCase() === DEV_WALLET.toLowerCase();

  useEffect(() => {
    fetchLeaderboard();
    fetchPools();
  }, []);

  const fetchPools = async () => {
    try {
      let rawApiUrl = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';
      let apiUrl = rawApiUrl.trim().replace(/^["']|["']$/g, '');
      if (apiUrl && !apiUrl.startsWith('http')) {
        apiUrl = apiUrl.replace(/^\/+/, '');
        apiUrl = `https://${apiUrl}`;
      }
      apiUrl = apiUrl.replace(/\/+$/, '');
      const response = await fetch(`${apiUrl}/pools`);
      const data = await response.json();
      const poolsMap = {};
      data.pools.forEach(pool => {
        poolsMap[pool.id] = pool.name;
      });
      setPools(poolsMap);
    } catch (error) {
      console.error('Error fetching pools:', error);
    }
  };

  const fetchLeaderboard = async () => {
    setLoading(true);
    try {
      let rawApiUrl = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';
      let apiUrl = rawApiUrl.trim().replace(/^["']|["']$/g, '');
      if (apiUrl && !apiUrl.startsWith('http')) {
        apiUrl = apiUrl.replace(/^\/+/, '');
        apiUrl = `https://${apiUrl}`;
      }
      apiUrl = apiUrl.replace(/\/+$/, '');
      const response = await fetch(`${apiUrl}/leaderboard`);
      const data = await response.json();
      setLeaderboard(data.leaderboard || []);
    } catch (error) {
      console.error('Error fetching leaderboard:', error);
      // Fallback to mock data
      setLeaderboard([
        { wallet: '0x1234567890abcdef', score: 1500, pool_id: 'daily' },
        { wallet: '0xabcdef1234567890', score: 1200, pool_id: 'daily' },
        { wallet: '0x567890abcdef1234', score: 950, pool_id: 'weekly' },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handlePayout = async () => {
    const poolName = pools[selectedPayoutPool] || selectedPayoutPool;
    if (!window.confirm(`This will end the current ${poolName} and distribute rewards to the top players. Continue?`)) {
      return;
    }

    try {
      setPayoutStatus(`Processing ${poolName} payouts...`);
      let rawApiUrl = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';
      let apiUrl = rawApiUrl.trim().replace(/^["']|["']$/g, '');
      if (apiUrl && !apiUrl.startsWith('http')) {
        apiUrl = apiUrl.replace(/^\/+/, '');
        apiUrl = `https://${apiUrl}`;
      }
      apiUrl = apiUrl.replace(/\/+$/, '');
      
      const response = await fetch(`${apiUrl}/distribute-rewards`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Dev-Wallet': walletAddress
        },
        body: JSON.stringify({
          pool_id: selectedPayoutPool,
          num_winners: 10
        }),
      });
      const data = await response.json();
      
      if (data.status === 'success') {
        setPayoutStatus(`✅ Success! Prize pool of ${data.total_prize} distributed. TX: ${data.contract_transaction}`);
        alert(`Rewards Distributed!\nTotal Prize: ${data.total_prize}\nWinners: ${data.num_winners}`);
        fetchLeaderboard(); // Refresh
      } else {
        setPayoutStatus(`❌ Error: ${data.message || data.error}`);
      }
    } catch (error) {
      setPayoutStatus('❌ Error calling payout API');
      console.error(error);
    }
  };

  return (
    <div className="leaderboard-wrapper">
      <button className="back-btn" onClick={onBack}>← Back</button>
      <h2 className="section-title">🏆 Leaderboard</h2>

      {isAdmin && (
        <div className="admin-payout-panel">
          <h3>Admin Payout Control</h3>
          <div className="payout-controls">
            <select 
              value={selectedPayoutPool} 
              onChange={(e) => setSelectedPayoutPool(e.target.value)}
              className="payout-select"
            >
              {Object.entries(pools).map(([id, name]) => (
                <option key={id} value={id}>{name}</option>
              ))}
            </select>
            <button 
              className="payout-btn"
              onClick={handlePayout}
            >
              💸 Payout Selected Pool
            </button>
          </div>
          {payoutStatus && <div className="payout-status">{payoutStatus}</div>}
        </div>
      )}
      
      {loading ? (
        <div className="loading">Loading...</div>
      ) : leaderboard.length === 0 ? (
        <div className="empty-state">No scores yet. Be the first!</div>
      ) : (
        <div className="leaderboard-list">
          {leaderboard.map((entry, index) => (
            <div 
              key={index} 
              className={`leaderboard-item rank-${index + 1}`}
            >
              <div className="rank">#{index + 1}</div>
              <div className="wallet">
                {entry.wallet.slice(0, 8)}...{entry.wallet.slice(-4)}
              </div>
              <div className="pool">
                {entry.pool_id ? pools[entry.pool_id] || 'Unknown Pool' : 'General'}
              </div>
              <div className="score">{entry.score} pts</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default Leaderboard;
