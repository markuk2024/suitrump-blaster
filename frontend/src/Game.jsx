import React, { useEffect, useRef, useState } from 'react';
import Phaser from 'phaser';
import './Game.css';

class GameScene extends Phaser.Scene {
  constructor() {
    super('GameScene');
  }

  preload() {
    // Create textures programmatically
    this.createPlayerTexture();
    this.createEnemyTexture();
    this.createBulletTexture();
  }

  createPlayerTexture() {
    const graphics = this.make.graphics({ x: 0, y: 0, add: false });
    
    // Main body - sleek spaceship
    graphics.fillStyle(0x667eea, 1);
    graphics.fillTriangle(25, 10, 5, 40, 25, 35);
    
    // Cockpit
    graphics.fillStyle(0x4a90e2, 1);
    graphics.fillTriangle(25, 15, 15, 30, 25, 28);
    
    // Wings
    graphics.fillStyle(0x5568d3, 1);
    graphics.fillTriangle(25, 25, 5, 35, 25, 30);
    graphics.fillTriangle(25, 25, 45, 35, 25, 30);
    
    // Engine glow
    graphics.fillStyle(0x00ff88, 0.8);
    graphics.fillCircle(25, 42, 5);
    
    graphics.generateTexture('player', 50, 50);
    graphics.destroy();
  }

  createEnemyTexture() {
    const graphics = this.make.graphics({ x: 0, y: 0, add: false });
    
    // Outer coin ring - Sui blue
    graphics.fillStyle(0x4da6ff, 1);
    graphics.fillCircle(20, 20, 20);
    
    // Inner circle - lighter blue
    graphics.fillStyle(0x66b3ff, 1);
    graphics.fillCircle(20, 20, 16);
    
    // White droplet pointing UP (inverted from before)
    graphics.fillStyle(0xffffff, 1);
    graphics.fillCircle(20, 26, 7);
    graphics.fillTriangle(14, 24, 26, 24, 20, 10);
    
    // Shine effect on coin
    graphics.fillStyle(0xffffff, 0.4);
    graphics.fillCircle(12, 28, 3);
    
    graphics.generateTexture('enemy', 40, 40);
    graphics.destroy();
  }

  createBulletTexture() {
    const graphics = this.make.graphics({ x: 0, y: 0, add: false });
    graphics.fillStyle(0x00ff88, 1);
    graphics.fillCircle(8, 8, 8);
    graphics.fillStyle(0x00ffcc, 1);
    graphics.fillCircle(8, 8, 4);
    graphics.generateTexture('bullet', 16, 16);
    graphics.destroy();
  }

  create() {
    this.score = 0;
    this.lives = 3;
    this.gameActive = true;
    this.startTime = Date.now();
    this.difficultyMultiplier = 1;
    this.spawnEvent = null;
    
    this.cameras.main.setBackgroundColor('#0a0a1a');
    
    // Add stars background
    this.createStarfield();
    
    // Initialize Web Audio context
    this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
    
    // Create player
    this.player = this.physics.add.sprite(400, 520, 'player');
    this.player.setCollideWorldBounds(true);
    
    // Create groups
    this.bullets = this.physics.add.group();
    this.enemies = this.physics.add.group();
    
    // Score text with background
    const scoreBg = this.add.graphics();
    scoreBg.fillStyle(0x000000, 0.7);
    scoreBg.fillRoundedRect(10, 10, 150, 40, 10);
    scoreBg.setDepth(1);
    
    this.scoreText = this.add.text(20, 18, 'Score: 0', {
      fontSize: '28px',
      color: '#00ff88',
      fontFamily: 'Arial',
      fontStyle: 'bold'
    });
    this.scoreText.setDepth(2);
    
    // Lives display
    this.livesText = this.add.text(650, 18, '❤️❤️❤️', {
      fontSize: '28px',
      fontFamily: 'Arial'
    });
    this.livesText.setDepth(2);
    
    // Instructions
    this.add.text(400, 580, 'Tap anywhere to shoot!', {
      fontSize: '16px',
      color: '#8888aa',
      fontFamily: 'Arial'
    }).setOrigin(0.5);
    
    // Start spawning enemies
    this.spawnEvent = this.time.addEvent({
      delay: 1500,
      callback: this.spawnEnemy,
      callbackScope: this,
      loop: true
    });
    
    // Click to shoot
    this.input.on('pointerdown', (pointer) => {
      if (this.gameActive) {
        this.shoot(pointer.x, pointer.y);
      }
    });
    
    // Collision detection
    this.physics.add.overlap(this.bullets, this.enemies, this.hitEnemy, null, this);
    
    console.log('Game scene created');
  }

  playShootSound() {
    // Simple shoot sound using oscillator
    const audioContext = this.audioContext;
    const oscillator = audioContext.createOscillator();
    const gainNode = audioContext.createGain();
    
    oscillator.connect(gainNode);
    gainNode.connect(audioContext.destination);
    
    oscillator.frequency.setValueAtTime(800, audioContext.currentTime);
    oscillator.frequency.exponentialRampToValueAtTime(200, audioContext.currentTime + 0.1);
    
    gainNode.gain.setValueAtTime(0.3, audioContext.currentTime);
    gainNode.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + 0.1);
    
    oscillator.start(audioContext.currentTime);
    oscillator.stop(audioContext.currentTime + 0.1);
  }

  playExplosionSound() {
    const audioContext = this.audioContext;
    const oscillator = audioContext.createOscillator();
    const gainNode = audioContext.createGain();
    
    oscillator.connect(gainNode);
    gainNode.connect(audioContext.destination);
    
    oscillator.frequency.setValueAtTime(150, audioContext.currentTime);
    oscillator.frequency.exponentialRampToValueAtTime(50, audioContext.currentTime + 0.2);
    
    gainNode.gain.setValueAtTime(0.4, audioContext.currentTime);
    gainNode.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + 0.2);
    
    oscillator.type = 'sawtooth';
    oscillator.start(audioContext.currentTime);
    oscillator.stop(audioContext.currentTime + 0.2);
  }

  playHitSound() {
    const audioContext = this.audioContext;
    const oscillator = audioContext.createOscillator();
    const gainNode = audioContext.createGain();
    
    oscillator.connect(gainNode);
    gainNode.connect(audioContext.destination);
    
    oscillator.frequency.setValueAtTime(200, audioContext.currentTime);
    
    gainNode.gain.setValueAtTime(0.3, audioContext.currentTime);
    gainNode.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + 0.15);
    
    oscillator.type = 'square';
    oscillator.start(audioContext.currentTime);
    oscillator.stop(audioContext.currentTime + 0.15);
  }

  createStarfield() {
    for (let i = 0; i < 100; i++) {
      const x = Phaser.Math.Between(0, 800);
      const y = Phaser.Math.Between(0, 600);
      const size = Phaser.Math.Between(1, 3);
      const star = this.add.rectangle(x, y, size, size, 0xffffff);
      star.setAlpha(Phaser.Math.FloatBetween(0.3, 0.8));
    }
  }

  spawnEnemy() {
    if (!this.gameActive) return;
    
    const x = Phaser.Math.Between(50, 750);
    const enemy = this.enemies.create(x, -30, 'enemy');
    const speed = Phaser.Math.Between(80, 150) * this.difficultyMultiplier;
    enemy.setVelocityY(speed);
    enemy.setInteractive();
  }

  updateDifficulty() {
    // Increase difficulty based on score (every 50 points)
    const scoreBasedMultiplier = 1 + Math.floor(this.score / 50) * 0.1;
    
    // Increase difficulty based on time (every 30 seconds)
    const timeElapsed = (Date.now() - this.startTime) / 1000;
    const timeBasedMultiplier = 1 + Math.floor(timeElapsed / 30) * 0.1;
    
    // Use the higher of the two multipliers, capped at 2.5x
    this.difficultyMultiplier = Math.min(Math.max(scoreBasedMultiplier, timeBasedMultiplier), 2.5);
    
    // Update spawn rate based on difficulty
    const newSpawnDelay = Math.max(500, 1500 - (this.difficultyMultiplier - 1) * 400);
    
    if (this.spawnEvent && this.spawnEvent.delay !== newSpawnDelay) {
      this.spawnEvent.remove();
      this.spawnEvent = this.time.addEvent({
        delay: newSpawnDelay,
        callback: this.spawnEnemy,
        callbackScope: this,
        loop: true
      });
    }
  }

  shoot(targetX, targetY) {
    const bullet = this.bullets.create(this.player.x, this.player.y - 30, 'bullet');
    const angle = Phaser.Math.Angle.Between(bullet.x, bullet.y, targetX, targetY);
    const speed = 600;
    bullet.setVelocity(Math.cos(angle) * speed, Math.sin(angle) * speed);
    
    // Play shoot sound
    this.playShootSound();
    
    // Remove bullet after 2 seconds
    this.time.delayedCall(2000, () => {
      if (bullet.active) {
        bullet.destroy();
      }
    });
  }

  hitEnemy(bullet, enemy) {
    // Create explosion effect
    this.createExplosion(enemy.x, enemy.y);
    
    // Play explosion sound
    this.playExplosionSound();
    
    bullet.destroy();
    enemy.destroy();
    this.score += 10;
    this.scoreText.setText('Score: ' + this.score);
    
    // Flash score text
    this.tweens.add({
      targets: this.scoreText,
      scale: 1.2,
      duration: 100,
      yoyo: true
    });
  }

  createExplosion(x, y) {
    const particles = this.add.particles(x, y, 'bullet', {
      speed: { min: 100, max: 200 },
      scale: { start: 1, end: 0 },
      lifespan: 500,
      blendMode: 'ADD',
      quantity: 10
    });
    this.time.delayedCall(500, () => particles.destroy());
  }

  update() {
    if (!this.gameActive) return;
    
    // Update difficulty based on score and time
    this.updateDifficulty();
    
    // Remove enemies that go off screen and decrease lives
    this.enemies.children.iterate((enemy) => {
      if (enemy && enemy.y > 650) {
        enemy.destroy();
        this.loseLife();
      }
    });
    
    // Remove bullets that go off screen
    this.bullets.children.iterate((bullet) => {
      if (bullet && (bullet.y < -50 || bullet.y > 650 || bullet.x < -50 || bullet.x > 850)) {
        bullet.destroy();
      }
    });
    
    const duration = (Date.now() - this.startTime) / 1000;
    if (duration > 120) {
      this.gameOver();
    }
  }

  loseLife() {
    this.lives--;
    this.updateLivesDisplay();
    
    // Play hit sound
    this.playHitSound();
    
    // Flash screen red
    this.cameras.main.flash(200, 255, 0, 0);
    
    if (this.lives <= 0) {
      this.gameOver();
    }
  }

  updateLivesDisplay() {
    const hearts = '❤️'.repeat(this.lives);
    this.livesText.setText(hearts);
  }

  gameOver() {
    this.gameActive = false;
    
    // Game over text
    const gameOverText = this.add.text(400, 250, 'GAME OVER', {
      fontSize: '64px',
      color: '#ff4444',
      fontFamily: 'Arial',
      fontStyle: 'bold',
      stroke: '#000000',
      strokeThickness: 6
    }).setOrigin(0.5);
    
    const finalScore = this.add.text(400, 320, 'Final Score: ' + this.score, {
      fontSize: '32px',
      color: '#ffffff',
      fontFamily: 'Arial',
      stroke: '#000000',
      strokeThickness: 4
    }).setOrigin(0.5);
    
    const duration = (Date.now() - this.startTime) / 1000;
    if (window.submitScoreCallback) {
      window.submitScoreCallback(this.score, Math.floor(duration));
    }
  }
}

const config = {
  type: Phaser.AUTO,
  width: 800,
  height: 600,
  parent: 'game-container',
  backgroundColor: '#0a0a1a',
  physics: {
    default: 'arcade',
    arcade: {
      gravity: { y: 0 },
      debug: false
    }
  },
  scene: GameScene,
  scale: {
    mode: Phaser.Scale.FIT,
    autoCenter: Phaser.Scale.CENTER_BOTH
  }
};

function Game({ pool, walletAddress, onGameOver, onBack }) {
  const gameRef = useRef(null);
  const isInitialized = useRef(false);
  
  useEffect(() => {
    if (isInitialized.current) {
      return;
    }
    isInitialized.current = true;
    
    // Initialize score callback
    window.submitScoreCallback = async (score, duration) => {
      console.log(`Submitting score: ${score}, duration: ${duration}`);
      try {
        const apiUrl = (import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000').replace(/\/$/, '');
        const response = await fetch(`${apiUrl}/submit-score`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            wallet: walletAddress,
            score: score,
            game_duration: duration,
            timestamp: Date.now(),
            pool_id: pool?.id || 'daily'
          }),
        });
        const data = await response.json();
        console.log('Score submission result:', data);
        onGameOver(score);
      } catch (error) {
        console.error('Error submitting score:', error);
        onGameOver(score);
      }
    };

    const newGame = new Phaser.Game(config);
    gameRef.current = newGame;
    
    return () => {
      if (gameRef.current) {
        gameRef.current.destroy(true);
        gameRef.current = null;
      }
      isInitialized.current = false;
      window.submitScoreCallback = null;
    };
  }, [walletAddress, pool?.id]);
  
  return (
    <div className="game-wrapper">
      <button className="back-btn" onClick={onBack}>← Back</button>
      <div id="game-container" className="game-canvas"></div>
      <div className="game-info">
        <p>Pool: {pool?.name || 'Daily Pool'}</p>
        <p>Entry Fee: {pool?.entryFee || '0.1 SUI'}</p>
        <p style={{fontSize: '12px', color: '#888'}}>Tap anywhere to shoot!</p>
      </div>
    </div>
  );
}

export default Game;
