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
  const [currentView, setCurrentView] = useState('home');
  const [selectedPool, setSelectedPool] = useState(null);
  const [connecting, setConnecting] = useState(false);

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
