import React, { useState } from 'react';
import { useCurrentAccount, useConnectWallet, useWallets, useSignAndExecuteTransaction } from '@mysten/dapp-kit';
import { Transaction } from '@mysten/sui/transactions';
import Game from './Game';
import Leaderboard from './Leaderboard';
import Pools from './Pools';
import './App.css';

function App() {
  const currentAccount = useCurrentAccount();
  const wallets = useWallets();
  const { mutate: connectWallet } = useConnectWallet();
  const { mutateAsync: signAndExecuteTransaction } = useSignAndExecuteTransaction();
  const [currentView, setCurrentView] = useState('home');
  const [selectedPool, setSelectedPool] = useState(null);
  const [connecting, setConnecting] = useState(false);
  const [adminMsg, setAdminMsg] = useState('');

  const handleInitializePools = async () => {
    try {
      setAdminMsg('Initializing pools... check wallet');
      const packageId = import.meta.env.VITE_SUI_PACKAGE_ID || "0x529e9c233a7f2f6cc5bcd8371735cba8e44d80a1d30c8bd0a29ea4b4be4d4b54";
      const devWallet = "0x4c2891f70f1317fed1198140e0f06f49593c82558b2b467e1717c23fee9131a6";
      
      const poolsToCreate = [
        { name: "Daily Pool", fee: "100000000" },
        { name: "Weekly Pool", fee: "500000000" },
        { name: "Monthly Pool", fee: "1000000000" }
      ];

      for (const pool of poolsToCreate) {
        const txb = new Transaction();
        txb.moveCall({
          target: `${packageId}::pool::create_pool`,
          arguments: [
            txb.pure.string(pool.name),
            txb.pure.u64(pool.fee),
            txb.pure.u8(2),
            txb.pure.address(devWallet)
          ]
        });
        
        const result = await signAndExecuteTransaction({ transaction: txb });
        console.log(`Created ${pool.name}. Result:`, result);
        setAdminMsg(prev => prev + `\n✅ ${pool.name} created! Check console for ID.`);
      }
      
      alert('Pools created! Open browser console (F12) to get the Object IDs.');
    } catch (error) {
      console.error('Admin Error:', error);
      setAdminMsg('Error: ' + error.message);
    }
  };

  const handleConnectWallet = () => {
    console.log('Available wallets:', wallets);
    console.log('Wallets array:', Array.isArray(wallets) ? wallets : 'Not an array');
    
    if (!wallets || !Array.isArray(wallets) || wallets.length === 0) {
      alert('No Sui wallet extension detected. Please install Sui Wallet or Slush.');
      window.open('https://suiwallet.com', '_blank');
      return;
    }
    
    const wallet = wallets[0];
    console.log('Using wallet:', wallet);
    
    setConnecting(true);
    connectWallet(
      { wallet },
      {
        onSuccess: () => {
          console.log('Wallet connected successfully');
          setConnecting(false);
        },
        onError: (error) => {
          console.error('Wallet connection error:', error);
          setConnecting(false);
          alert('Failed to connect wallet. Please try again.');
        },
      }
    );
  };

  const walletAddress = currentAccount?.address || '';

  return (
    <div className="app">
      <header className="header">
        <h1 className="title">🚀 Sui Blaster v2</h1>
        <button 
          className="wallet-btn"
          onClick={currentAccount ? null : handleConnectWallet}
          disabled={connecting}
        >
          {currentAccount 
            ? `✅ ${walletAddress.slice(0, 8)}...${walletAddress.slice(-4)}` 
            : connecting ? 'Connecting...' : '🔗 Connect Wallet'}
        </button>
      </header>

      <div className="main-content">
        {currentView === 'home' && (
          <div className="home-view">
            <div className="wallet-info">
              {currentAccount ? (
                <p>Wallet: {walletAddress.slice(0, 8)}...{walletAddress.slice(-4)}</p>
              ) : (
                <p>Connect Sui Wallet extension to play for real rewards</p>
              )}
            </div>
            
            <div className="action-buttons">
              <button 
                className="action-btn primary"
                onClick={() => setCurrentView('pools')}
              >
                🎮 Join Competition
              </button>
              <button 
                className="action-btn secondary"
                onClick={() => setCurrentView('leaderboard')}
              >
                🏆 Leaderboard
              </button>
            </div>

            <div className="info-section">
              <h3>How to Play</h3>
              <ul>
                <li>Join a competition pool by paying SUI</li>
                <li>Control your ship with touch controls</li>
                <li>Shoot enemies to score points</li>
                <li>Top players win prize pool rewards</li>
              </ul>
            </div>

            {currentAccount && (
              <div style={{ marginTop: '40px', borderTop: '1px solid #333', paddingTop: '20px' }}>
                <p style={{ fontSize: '12px', color: '#666' }}>Admin Tool:</p>
                <button 
                  onClick={handleInitializePools}
                  style={{ backgroundColor: '#333', color: '#fff', fontSize: '12px', padding: '5px 10px', borderRadius: '4px' }}
                >
                  ⚙️ Initialize Production Pools
                </button>
                {adminMsg && <pre style={{ fontSize: '10px', color: '#888', marginTop: '10px' }}>{adminMsg}</pre>}
              </div>
            )}
          </div>
        )}

        {currentView === 'pools' && (
          <Pools 
            walletAddress={currentAccount ? walletAddress : null}
            onSelectPool={(pool) => {
              setSelectedPool(pool);
              setCurrentView('game');
            }}
            onBack={() => setCurrentView('home')}
          />
        )}

        {currentView === 'game' && selectedPool && (
          <Game 
            pool={selectedPool}
            walletAddress={currentAccount ? walletAddress : null}
            onGameOver={(score) => {
              setCurrentView('leaderboard');
            }}
            onBack={() => setCurrentView('pools')}
          />
        )}

        {currentView === 'leaderboard' && (
          <Leaderboard onBack={() => setCurrentView('home')} />
        )}
      </div>
    </div>
  );
}

export default App;
