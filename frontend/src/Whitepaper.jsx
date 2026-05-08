import React from 'react';
import './Whitepaper.css';

function Whitepaper({ onBack }) {
  return (
    <div className="whitepaper-container">
      <button className="back-btn" onClick={onBack}>← Back</button>
      <div className="whitepaper-content">
        <h1>🛰️ SuiTrump Blaster v2 - Whitepaper</h1>
        <p className="subtitle">Official Rules, Payout Structure, and Tokenomics</p>

        <section>
          <h2>1. Introduction</h2>
          <p>
            SuiTrump Blaster v2 is a fast-paced, survival space shooter built on the Sui Blockchain. 
            Players compete in time-limited pools to achieve the highest scores and win SUITRUMP rewards from collective prize pools.
          </p>
        </section>

        <section>
          <h2>2. Gameplay Mechanics</h2>
          <ul>
            <li><strong>Entry:</strong> Players must pay the entry fee in SUI to join a competition pool.</li>
            <li><strong>Lives:</strong> Each player starts with 3 lives. Letting an enemy pass the bottom of the screen costs 1 life.</li>
            <li><strong>Duration:</strong> A single game session lasts for a maximum of 120 seconds.</li>
            <li><strong>Scoring:</strong> Destroying enemies increases your score. Difficulty scales over time and score.</li>
          </ul>
        </section>

        <section>
          <h2>3. Competition Pools</h2>
          <div className="pool-grid">
            <div className="pool-rule">
              <h3>📅 Daily Pool</h3>
              <p><strong>Duration:</strong> 24 Hours</p>
              <p><strong>Payout:</strong> 1 Winner (100% of prize pool)</p>
            </div>
            <div className="pool-rule">
              <h3>🗓️ Weekly Pool</h3>
              <p><strong>Duration:</strong> 7 Days</p>
              <p><strong>Payout:</strong> Top 3 Players (Split 33.33% each)</p>
            </div>
            <div className="pool-rule">
              <h3>🌕 Monthly Pool</h3>
              <p><strong>Duration:</strong> 28 Days</p>
              <p><strong>Payout:</strong> Top 4 Players (Split 25% each)</p>
            </div>
          </div>
        </section>

        <section>
          <h2>4. Reward Distribution & Fees</h2>
          <p>
            Prize pools are dynamic and grow with every player entry. Rewards are distributed automatically via smart contract at the end of each pool's duration.
          </p>
          <div className="fee-box">
            <h3>🛠️ Developer Fee</h3>
            <p>
              A <strong>2.5% Developer Fee</strong> is deducted from the total prize pool before any rewards are distributed. 
              This fee is used to cover server costs, RPC maintenance, and the continued development of the SuiTrump Blaster ecosystem.
            </p>
          </div>
          <p>
            <em>Example: If a Daily Pool has 10 SUI, 0.25 SUI is sent to the developer, and 9.75 SUI is sent to the 1st place winner.</em>
          </p>
        </section>

        <section>
          <h2>5. Anti-Cheat & Fair Play</h2>
          <p>
            To ensure a fair environment for all players, SuiTrump Blaster employs several security measures:
          </p>
          <ul>
            <li><strong>Transaction Verification:</strong> Every entry is verified on the Sui blockchain before score submission is allowed.</li>
            <li><strong>Backend Validation:</strong> Scores are checked against game duration and maximum possible points per second.</li>
            <li><strong>Automated Payouts:</strong> Distributions are handled by secure backend logic calling verified Move smart contracts.</li>
          </ul>
        </section>

        <section>
          <h2>6. Disclaimer & Risks</h2>
          <p>
            SuiTrump Blaster v2 is a decentralized application built on the Sui Network. 
            Cryptocurrency investments carry inherent risks. Please only play with SUI you can afford to lose. 
            The developers are not responsible for network congestion or wallet-side technical issues.
          </p>
        </section>

        <footer>
          <p>&copy; 2024 SuiTrump Blaster v2. Built on Sui Mainnet.</p>
        </footer>
      </div>
    </div>
  );
}

export default Whitepaper;
