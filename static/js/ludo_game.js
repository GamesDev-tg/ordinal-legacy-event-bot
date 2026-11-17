/**
 * Ordinal Legacy - Multiplayer Ludo Arena (2 to 8 Players)
 * High-performance HTML5 Canvas implementation with smooth animations,
 * procedural Web Audio SFX, AI bots, and pass & play modes.
 */
class LudoGame {
    constructor(canvas, onGameOver) {
        this.canvas = canvas;
        this.ctx = canvas.getContext('2d');
        this.onGameOver = onGameOver;
        this.running = false;
        this.startTime = 0;
        
        // Audio synthesis for rich gameplay sound FX without external files
        this.audioCtx = null;
        try {
            const AudioContext = window.AudioContext || window.webkitAudioContext;
            if (AudioContext) this.audioCtx = new AudioContext();
        } catch (e) {}

        // Colors palette supporting up to 8 players
        this.colorConfigs = [
            { id: 'red', name: 'Red', color: '#EF4444', glow: 'rgba(239, 68, 68, 0.6)', light: '#FCA5A5' },
            { id: 'green', name: 'Green', color: '#10B981', glow: 'rgba(16, 185, 129, 0.6)', light: '#6EE7B7' },
            { id: 'yellow', name: 'Yellow', color: '#F59E0B', glow: 'rgba(245, 158, 11, 0.6)', light: '#FDE68A' },
            { id: 'blue', name: 'Blue', color: '#3B82F6', glow: 'rgba(59, 130, 246, 0.6)', light: '#93C5FD' },
            { id: 'orange', name: 'Orange', color: '#F97316', glow: 'rgba(249, 115, 22, 0.6)', light: '#FDBA74' },
            { id: 'purple', name: 'Purple', color: '#A855F7', glow: 'rgba(168, 85, 247, 0.6)', light: '#D8B4FE' },
            { id: 'cyan', name: 'Cyan', color: '#06B6D4', glow: 'rgba(6, 182, 212, 0.6)', light: '#67E8F9' },
            { id: 'pink', name: 'Pink', color: '#EC4899', glow: 'rgba(236, 72, 153, 0.6)', light: '#F9A8D4' }
        ];

        this.numPlayers = 4; // Default 4, supports 2, 4, 6, 8
        this.mode = 'ai'; // 'ai' or 'pass_play'
        this.players = [];
        this.currentTurn = 0;
        this.diceRoll = null;
        this.isRolling = false;
        this.rollAnimProgress = 0;
        this.consecutiveSixes = 0;
        this.movablePawns = [];
        this.particles = [];
        this.confetti = [];
        this.logs = [];
        this.gameOver = false;
        this.winners = [];
        this.selectedPlayerCount = 4;

        this.handleCanvasClick = this.handleCanvasClick.bind(this);
    }

    start() {
        this.running = true;
        this.startTime = Date.now();
        this.initGame(this.selectedPlayerCount);
        this.canvas.addEventListener('click', this.handleCanvasClick);
        this.canvas.addEventListener('touchstart', (e) => {
            if (e.touches && e.touches[0]) {
                const rect = this.canvas.getBoundingClientRect();
                this.handleClickAt(e.touches[0].clientX - rect.left, e.touches[0].clientY - rect.top);
            }
        }, { passive: false });
        this.animate = this.animate.bind(this);
        requestAnimationFrame(this.animate);
    }

    stop() {
        this.running = false;
        this.canvas.removeEventListener('click', this.handleCanvasClick);
    }

    initGame(numPlayers) {
        this.numPlayers = numPlayers;
        this.circuitLen = numPlayers <= 4 ? 52 : 80;
        this.safeStars = numPlayers <= 4 ? [0, 8, 13, 21, 26, 34, 39, 47] : [0, 8, 10, 18, 20, 28, 30, 38, 40, 48, 50, 58, 60, 68, 70, 78];
        
        let colorSeq = [0, 1, 2, 3];
        if (numPlayers === 2) colorSeq = [0, 2];
        else if (numPlayers === 4) colorSeq = [0, 1, 2, 3];
        else if (numPlayers === 6) colorSeq = [0, 4, 2, 1, 3, 5];
        else if (numPlayers === 8) colorSeq = [0, 4, 2, 1, 6, 3, 5, 7];

        this.players = [];
        for (let i = 0; i < numPlayers; i++) {
            const cIdx = colorSeq[i];
            const cfg = this.colorConfigs[cIdx];
            const startStep = numPlayers <= 4 ? [0, 13, 26, 39][i] : i * 10;
            const homeEntry = (startStep - 2 + this.circuitLen) % this.circuitLen;
            const isAi = (i !== 0); // Player 0 is Human, rest AI

            const pawns = [];
            for (let p = 0; p < 4; p++) {
                pawns.push({
                    id: p,
                    state: 'yard', // 'yard', 'track', 'home', 'goal'
                    pos: -1,
                    stepsTraveled: 0,
                    x: 0,
                    y: 0,
                    targetX: 0,
                    targetY: 0,
                    animStep: 1
                });
            }

            this.players.push({
                id: i,
                name: i === 0 ? "You (Human)" : `Bot ${i} (AI)`,
                isAi: isAi,
                colorCfg: cfg,
                colorIdx: cIdx,
                startStep: startStep,
                homeEntry: homeEntry,
                pawns: pawns,
                rank: null
            });
        }

        this.currentTurn = 0;
        this.diceRoll = null;
        this.isRolling = false;
        this.consecutiveSixes = 0;
        this.movablePawns = [];
        this.gameOver = false;
        this.winners = [];
        this.logs = [`🎲 ${this.numPlayers}-Player Ludo Match Started!`];
        this.playSound('start');
    }

    playSound(type) {
        if (!this.audioCtx) return;
        try {
            if (this.audioCtx.state === 'suspended') this.audioCtx.resume();
            const now = this.audioCtx.currentTime;
            const osc = this.audioCtx.createOscillator();
            const gain = this.audioCtx.createGain();
            osc.connect(gain);
            gain.connect(this.audioCtx.destination);

            if (type === 'roll') {
                osc.type = 'triangle';
                osc.frequency.setValueAtTime(220, now);
                osc.frequency.exponentialRampToValueAtTime(440, now + 0.15);
                gain.gain.setValueAtTime(0.12, now);
                gain.gain.exponentialRampToValueAtTime(0.01, now + 0.15);
                osc.start(now);
                osc.stop(now + 0.15);
            } else if (type === 'move') {
                osc.type = 'sine';
                osc.frequency.setValueAtTime(480, now);
                osc.frequency.exponentialRampToValueAtTime(720, now + 0.12);
                gain.gain.setValueAtTime(0.15, now);
                gain.gain.exponentialRampToValueAtTime(0.01, now + 0.12);
                osc.start(now);
                osc.stop(now + 0.12);
            } else if (type === 'capture') {
                osc.type = 'sawtooth';
                osc.frequency.setValueAtTime(300, now);
                osc.frequency.linearRampToValueAtTime(100, now + 0.25);
                gain.gain.setValueAtTime(0.2, now);
                gain.gain.exponentialRampToValueAtTime(0.01, now + 0.25);
                osc.start(now);
                osc.stop(now + 0.25);
            } else if (type === 'goal') {
                osc.type = 'sine';
                osc.frequency.setValueAtTime(523.25, now);
                osc.frequency.setValueAtTime(659.25, now + 0.1);
                osc.frequency.setValueAtTime(783.99, now + 0.2);
                gain.gain.setValueAtTime(0.2, now);
                gain.gain.exponentialRampToValueAtTime(0.01, now + 0.4);
                osc.start(now);
                osc.stop(now + 0.4);
            }
        } catch (e) {}
    }

    handleCanvasClick(e) {
        const rect = this.canvas.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;
        this.handleClickAt(x, y);
    }

    handleClickAt(x, y) {
        if (this.gameOver) return;

        // 1. Check Capacity switcher buttons at the top
        const btnY = 16;
        const counts = [2, 4, 6, 8];
        const btnW = 54;
        const startX = (this.canvas.width - (counts.length * (btnW + 8))) / 2;
        for (let i = 0; i < counts.length; i++) {
            const bx = startX + i * (btnW + 8);
            if (x >= bx && x <= bx + btnW && y >= btnY && y <= btnY + 28) {
                if (this.selectedPlayerCount !== counts[i]) {
                    this.selectedPlayerCount = counts[i];
                    this.initGame(this.selectedPlayerCount);
                }
                return;
            }
        }

        const curr = this.players[this.currentTurn];
        if (curr.isAi) return; // Wait for bot turn

        // 2. Check Dice Roll Tap
        const diceBox = this.getDiceBounds();
        if (x >= diceBox.x && x <= diceBox.x + diceBox.w && y >= diceBox.y && y <= diceBox.y + diceBox.h) {
            if (!this.diceRoll && !this.isRolling) {
                this.rollDice();
            }
            return;
        }

        // 3. Check Pawns Tap if awaiting choice
        if (this.diceRoll && this.movablePawns.length > 0) {
            for (const pId of this.movablePawns) {
                const pawn = curr.pawns[pId];
                const dist = Math.hypot(x - pawn.x, y - pawn.y);
                if (dist <= 22) {
                    this.executePawnMove(pId);
                    return;
                }
            }
        }
    }

    getDiceBounds() {
        const size = 56;
        return {
            x: (this.canvas.width - size) / 2,
            y: this.canvas.height - 76,
            w: size,
            h: size
        };
    }

    rollDice() {
        if (this.isRolling || this.gameOver) return;
        this.isRolling = true;
        this.rollAnimProgress = 0;
        this.playSound('roll');

        const animInterval = setInterval(() => {
            this.rollAnimProgress += 0.2;
            if (this.rollAnimProgress >= 1.0) {
                clearInterval(animInterval);
                this.isRolling = false;
                this.diceRoll = Math.floor(Math.random() * 6) + 1;
                
                const curr = this.players[this.currentTurn];
                if (this.diceRoll === 6) this.consecutiveSixes++;
                else this.consecutiveSixes = 0;

                this.logs.push(`🎲 ${curr.name} rolled a ${this.diceRoll}!`);

                if (this.consecutiveSixes >= 3) {
                    this.logs.push(`⚠️ 3 consecutive sixes! Turn passed.`);
                    this.advanceTurn(false);
                    return;
                }

                this.movablePawns = this.getMovablePawns(this.currentTurn, this.diceRoll);
                if (this.movablePawns.length === 0) {
                    this.logs.push(`⏭️ No valid moves. Turn passed.`);
                    setTimeout(() => this.advanceTurn(false), 700);
                } else if (this.movablePawns.length === 1 && curr.isAi) {
                    setTimeout(() => this.executePawnMove(this.movablePawns[0]), 500);
                } else if (curr.isAi) {
                    // AI chooses best move
                    setTimeout(() => {
                        const chosen = this.aiChoosePawn(curr, this.movablePawns, this.diceRoll);
                        this.executePawnMove(chosen);
                    }, 650);
                }
            }
        }, 35);
    }

    getMovablePawns(playerIdx, roll) {
        const player = this.players[playerIdx];
        const movable = [];
        for (const pawn of player.pawns) {
            if (pawn.state === 'yard') {
                if (roll === 6) movable.push(pawn.id);
            } else if (pawn.state === 'track') {
                if (pawn.stepsTraveled + roll > this.circuitLen) {
                    const overshoot = (pawn.stepsTraveled + roll) - (this.circuitLen + 1);
                    if (overshoot <= 5) movable.push(pawn.id);
                } else {
                    movable.push(pawn.id);
                }
            } else if (pawn.state === 'home') {
                if (pawn.pos + roll <= 5) movable.push(pawn.id);
            }
        }
        return movable;
    }

    aiChoosePawn(player, movable, roll) {
        let bestScore = -999;
        let chosen = movable[0];

        for (const pId of movable) {
            const pawn = player.pawns[pId];
            let score = 0;
            if (pawn.state === 'yard' && roll === 6) {
                score += 70; // High value to enter board
            } else if (pawn.state === 'track') {
                const targetPos = (pawn.pos + roll) % this.circuitLen;
                // Capture check
                if (!this.safeStars.includes(targetPos)) {
                    for (const opp of this.players) {
                        if (opp.id !== player.id) {
                            for (const op of opp.pawns) {
                                if (op.state === 'track' && op.pos === targetPos) score += 180;
                            }
                        }
                    }
                }
                if (this.safeStars.includes(targetPos)) score += 50;
                score += pawn.stepsTraveled * 1.5;
            } else if (pawn.state === 'home') {
                if (pawn.pos + roll === 5) score += 140; // Goal reached
                else score += 40;
            }

            if (score > bestScore) {
                bestScore = score;
                chosen = pId;
            }
        }
        return chosen;
    }

    executePawnMove(pawnId) {
        const curr = this.players[this.currentTurn];
        const roll = this.diceRoll;
        const pawn = curr.pawns[pawnId];
        let bonusTurn = (roll === 6 && this.consecutiveSixes < 3);

        if (pawn.state === 'yard') {
            pawn.state = 'track';
            pawn.pos = curr.startStep;
            pawn.stepsTraveled = 1;
            this.playSound('move');
            this.spawnSparks(pawn.x, pawn.y, curr.colorCfg.color, 12);
        } else if (pawn.state === 'track') {
            if (pawn.stepsTraveled + roll > this.circuitLen) {
                const homeStep = (pawn.stepsTraveled + roll) - (this.circuitLen + 1);
                if (homeStep === 5) {
                    pawn.state = 'goal';
                    pawn.pos = 5;
                    pawn.stepsTraveled += roll;
                    this.playSound('goal');
                    this.spawnConfetti();
                } else {
                    pawn.state = 'home';
                    pawn.pos = homeStep;
                    pawn.stepsTraveled += roll;
                    this.playSound('move');
                }
            } else {
                pawn.pos = (pawn.pos + roll) % this.circuitLen;
                pawn.stepsTraveled += roll;
                this.playSound('move');

                // Check capture
                if (!this.safeStars.includes(pawn.pos)) {
                    for (const opp of this.players) {
                        if (opp.id !== curr.id) {
                            for (const op of opp.pawns) {
                                if (op.state === 'track' && op.pos === pawn.pos) {
                                    op.state = 'yard';
                                    op.pos = -1;
                                    op.stepsTraveled = 0;
                                    bonusTurn = true;
                                    this.playSound('capture');
                                    this.spawnSparks(pawn.x, pawn.y, '#F59E0B', 25);
                                    this.logs.push(`💥 ${curr.name} captured ${opp.name}'s pawn!`);
                                }
                            }
                        }
                    }
                }
            }
        } else if (pawn.state === 'home') {
            pawn.pos += roll;
            if (pawn.pos === 5) {
                pawn.state = 'goal';
                this.playSound('goal');
                this.spawnConfetti();
            } else {
                this.playSound('move');
            }
        }

        // Check if player won
        const allGoal = curr.pawns.every(p => p.state === 'goal');
        if (allGoal && curr.rank === null) {
            const rank = this.winners.length + 1;
            curr.rank = rank;
            this.winners.push(curr.id);
            this.logs.push(`🎉 <b>${curr.name} finished at Rank #${rank}!</b>`);

            if (this.winners.length >= 1 || this.players.filter(p => p.rank === null).length <= 1) {
                this.gameOver = true;
                const duration = Date.now() - this.startTime;
                const finalScore = curr.id === 0 ? 3 : (this.winners.includes(0) ? 2 : 1);
                setTimeout(() => {
                    if (this.onGameOver) this.onGameOver(finalScore, Math.max(3500, duration));
                }, 1600);
                return;
            }
        }

        this.diceRoll = null;
        this.movablePawns = [];
        this.advanceTurn(bonusTurn);
    }

    advanceTurn(bonusTurn) {
        this.diceRoll = null;
        this.movablePawns = [];

        if (this.gameOver) return;

        if (bonusTurn) {
            this.logs.push(`🌟 ${this.players[this.currentTurn].name} gets a BONUS ROLL!`);
            if (this.players[this.currentTurn].isAi) {
                setTimeout(() => this.rollDice(), 700);
            }
            return;
        }

        this.consecutiveSixes = 0;
        let nextTurn = (this.currentTurn + 1) % this.numPlayers;
        while (this.players[nextTurn].rank !== null) {
            nextTurn = (nextTurn + 1) % this.numPlayers;
        }
        this.currentTurn = nextTurn;

        if (this.players[this.currentTurn].isAi && !this.gameOver) {
            setTimeout(() => this.rollDice(), 700);
        }
    }

    spawnSparks(x, y, color, count) {
        for (let i = 0; i < count; i++) {
            const angle = Math.random() * Math.PI * 2;
            const speed = 2 + Math.random() * 4;
            this.particles.push({
                x: x,
                y: y,
                vx: Math.cos(angle) * speed,
                vy: Math.sin(angle) * speed,
                color: color,
                alpha: 1,
                decay: 0.03 + Math.random() * 0.03
            });
        }
    }

    spawnConfetti() {
        const colors = ['#EF4444', '#10B981', '#F59E0B', '#3B82F6', '#A855F7', '#EC4899'];
        for (let i = 0; i < 40; i++) {
            this.confetti.push({
                x: this.canvas.width / 2 + (Math.random() - 0.5) * 80,
                y: this.canvas.height / 2 + (Math.random() - 0.5) * 80,
                vx: (Math.random() - 0.5) * 8,
                vy: -4 - Math.random() * 6,
                size: 4 + Math.random() * 4,
                color: colors[Math.floor(Math.random() * colors.length)],
                alpha: 1
            });
        }
    }

    animate() {
        if (!this.running) return;
        this.render();
        requestAnimationFrame(this.animate);
    }

    render() {
        const ctx = this.ctx;
        const w = this.canvas.width;
        const h = this.canvas.height;

        ctx.clearRect(0, 0, w, h);

        // Background
        const bgGrad = ctx.createRadialGradient(w/2, h/2, 40, w/2, h/2, w);
        bgGrad.addColorStop(0, '#111827');
        bgGrad.addColorStop(1, '#070A0F');
        ctx.fillStyle = bgGrad;
        ctx.fillRect(0, 0, w, h);

        // 1. Capacity Switcher Header
        this.renderHeader(ctx, w);

        // 2. Render Board Layout
        const boardCenterY = h / 2 - 10;
        const boardRadius = Math.min(w * 0.44, 185);
        this.renderBoard(ctx, w / 2, boardCenterY, boardRadius);

        // 3. Render Pawns
        this.renderPawns(ctx, w / 2, boardCenterY, boardRadius);

        // 4. Render Particle effects
        this.renderParticles(ctx);

        // 5. Render Bottom Control Strip (Dice & Turn status)
        this.renderControlStrip(ctx, w, h);
    }

    renderHeader(ctx, w) {
        const counts = [2, 4, 6, 8];
        const btnW = 54;
        const btnH = 26;
        const startX = (w - (counts.length * (btnW + 8))) / 2;

        for (let i = 0; i < counts.length; i++) {
            const bx = startX + i * (btnW + 8);
            const active = (this.selectedPlayerCount === counts[i]);

            ctx.fillStyle = active ? '#F59E0B' : '#1E293B';
            ctx.beginPath();
            ctx.roundRect(bx, 16, btnW, btnH, 6);
            ctx.fill();

            ctx.strokeStyle = active ? '#FDE68A' : '#334155';
            ctx.lineWidth = 1;
            ctx.stroke();

            ctx.font = 'bold 11px Inter, sans-serif';
            ctx.fillStyle = active ? '#0F172A' : '#94A3B8';
            ctx.textAlign = 'center';
            ctx.fillText(`${counts[i]} Players`, bx + btnW / 2, 33);
        }
    }

    renderBoard(ctx, cx, cy, radius) {
        // Outer decorative ring
        ctx.beginPath();
        ctx.arc(cx, cy, radius + 14, 0, Math.PI * 2);
        ctx.strokeStyle = '#1E293B';
        ctx.lineWidth = 4;
        ctx.stroke();

        ctx.beginPath();
        ctx.arc(cx, cy, radius + 10, 0, Math.PI * 2);
        ctx.strokeStyle = 'rgba(245, 158, 11, 0.2)';
        ctx.lineWidth = 2;
        ctx.stroke();

        // Outer Track Circuit Cells
        const totalCells = this.circuitLen;
        for (let i = 0; i < totalCells; i++) {
            const angle = (i / totalCells) * Math.PI * 2 - Math.PI / 2;
            const x = cx + Math.cos(angle) * radius;
            const y = cy + Math.sin(angle) * radius;

            const isSafe = this.safeStars.includes(i);
            ctx.beginPath();
            ctx.arc(x, y, 7.5, 0, Math.PI * 2);
            ctx.fillStyle = isSafe ? '#F59E0B' : '#1E293B';
            ctx.fill();
            ctx.strokeStyle = isSafe ? '#FEF08A' : '#334155';
            ctx.lineWidth = 1.5;
            ctx.stroke();

            if (isSafe) {
                ctx.fillStyle = '#FFFFFF';
                ctx.font = 'bold 8px Inter, sans-serif';
                ctx.textAlign = 'center';
                ctx.fillText('★', x, y + 3);
            }
        }

        // Center Akhand Goal Shrine
        const centerGrad = ctx.createRadialGradient(cx, cy, 2, cx, cy, 32);
        centerGrad.addColorStop(0, '#FEF08A');
        centerGrad.addColorStop(0.6, '#F59E0B');
        centerGrad.addColorStop(1, '#92400E');
        ctx.beginPath();
        ctx.arc(cx, cy, 30, 0, Math.PI * 2);
        ctx.fillStyle = centerGrad;
        ctx.fill();
        ctx.strokeStyle = '#FDE68A';
        ctx.lineWidth = 2.5;
        ctx.stroke();

        ctx.fillStyle = '#1E1B4B';
        ctx.font = 'bold 15px sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText('🏆', cx, cy + 5);

        // Player Yards and Colored Home Corridors
        for (let pIdx = 0; pIdx < this.numPlayers; pIdx++) {
            const player = this.players[pIdx];
            const angle = (player.startStep / totalCells) * Math.PI * 2 - Math.PI / 2;
            
            // Base Yard
            const yardDist = radius * 0.62;
            const yx = cx + Math.cos(angle) * yardDist;
            const yy = cy + Math.sin(angle) * yardDist;

            ctx.beginPath();
            ctx.arc(yx, yy, 24, 0, Math.PI * 2);
            ctx.fillStyle = '#0F172A';
            ctx.fill();
            ctx.strokeStyle = player.colorCfg.color;
            ctx.lineWidth = 2.5;
            ctx.stroke();

            // Home Corridor Steps leading to center
            for (let step = 0; step < 5; step++) {
                const stepDist = 36 + step * ((radius - 46) / 5.5);
                const hx = cx + Math.cos(angle) * stepDist;
                const hy = cy + Math.sin(angle) * stepDist;

                ctx.beginPath();
                ctx.arc(hx, hy, 6, 0, Math.PI * 2);
                ctx.fillStyle = player.colorCfg.color;
                ctx.fill();
                ctx.strokeStyle = player.colorCfg.light;
                ctx.lineWidth = 1;
                ctx.stroke();
            }
        }
    }

    renderPawns(ctx, cx, cy, radius) {
        const totalCells = this.circuitLen;

        for (let pIdx = 0; pIdx < this.numPlayers; pIdx++) {
            const player = this.players[pIdx];
            const isTurn = (pIdx === this.currentTurn);
            const yardAngle = (player.startStep / totalCells) * Math.PI * 2 - Math.PI / 2;
            const yardDist = radius * 0.62;
            const yx = cx + Math.cos(yardAngle) * yardDist;
            const yy = cy + Math.sin(yardAngle) * yardDist;

            for (const pawn of player.pawns) {
                let px = yx;
                let py = yy;

                if (pawn.state === 'yard') {
                    // Offset 4 pawns within base
                    const offsets = [
                        { dx: -10, dy: -10 },
                        { dx: 10, dy: -10 },
                        { dx: -10, dy: 10 },
                        { dx: 10, dy: 10 }
                    ];
                    px = yx + offsets[pawn.id].dx;
                    py = yy + offsets[pawn.id].dy;
                } else if (pawn.state === 'track') {
                    const angle = (pawn.pos / totalCells) * Math.PI * 2 - Math.PI / 2;
                    px = cx + Math.cos(angle) * radius;
                    py = cy + Math.sin(angle) * radius;
                } else if (pawn.state === 'home') {
                    const stepDist = 36 + pawn.pos * ((radius - 46) / 5.5);
                    px = cx + Math.cos(yardAngle) * stepDist;
                    py = cy + Math.sin(yardAngle) * stepDist;
                } else if (pawn.state === 'goal') {
                    px = cx + (pawn.id - 1.5) * 8;
                    py = cy;
                }

                pawn.x = px;
                pawn.y = py;

                // Pulsing highlight if movable
                const isMovable = isTurn && this.movablePawns.includes(pawn.id);
                if (isMovable) {
                    ctx.save();
                    const pulse = 10 + Math.sin(Date.now() / 150) * 3;
                    ctx.beginPath();
                    ctx.arc(px, py, pulse + 4, 0, Math.PI * 2);
                    ctx.fillStyle = player.colorCfg.glow;
                    ctx.fill();
                    ctx.restore();
                }

                // Render Pawn Chip
                ctx.beginPath();
                ctx.arc(px, py, 9, 0, Math.PI * 2);
                ctx.fillStyle = player.colorCfg.color;
                ctx.fill();
                ctx.strokeStyle = '#FFFFFF';
                ctx.lineWidth = 2;
                ctx.stroke();

                // Inner crown or dot
                ctx.beginPath();
                ctx.arc(px, py, 4, 0, Math.PI * 2);
                ctx.fillStyle = player.colorCfg.light;
                ctx.fill();
            }
        }
    }

    renderParticles(ctx) {
        for (let i = this.particles.length - 1; i >= 0; i--) {
            const p = this.particles[i];
            p.x += p.vx;
            p.y += p.vy;
            p.alpha -= p.decay;

            if (p.alpha <= 0) {
                this.particles.splice(i, 1);
                continue;
            }

            ctx.save();
            ctx.globalAlpha = p.alpha;
            ctx.fillStyle = p.color;
            ctx.beginPath();
            ctx.arc(p.x, p.y, 3, 0, Math.PI * 2);
            ctx.fill();
            ctx.restore();
        }

        for (let i = this.confetti.length - 1; i >= 0; i--) {
            const c = this.confetti[i];
            c.x += c.vx;
            c.y += c.vy;
            c.vy += 0.2; // gravity
            c.alpha -= 0.015;

            if (c.alpha <= 0) {
                this.confetti.splice(i, 1);
                continue;
            }

            ctx.save();
            ctx.globalAlpha = c.alpha;
            ctx.fillStyle = c.color;
            ctx.fillRect(c.x, c.y, c.size, c.size);
            ctx.restore();
        }
    }

    renderControlStrip(ctx, w, h) {
        const curr = this.players[this.currentTurn];

        // Status line
        ctx.font = 'bold 13px Inter, sans-serif';
        ctx.fillStyle = '#F8FAFC';
        ctx.textAlign = 'center';
        const logMsg = this.logs.length > 0 ? this.logs[this.logs.length - 1].replace(/<[^>]+>/g, '') : '';
        ctx.fillText(logMsg, w / 2, h - 90);

        // Dice 3D Box
        const d = this.getDiceBounds();
        ctx.save();
        ctx.shadowColor = curr.colorCfg.glow;
        ctx.shadowBlur = 12;

        ctx.fillStyle = '#1E293B';
        ctx.beginPath();
        ctx.roundRect(d.x, d.y, d.w, d.h, 12);
        ctx.fill();
        ctx.strokeStyle = curr.colorCfg.color;
        ctx.lineWidth = 3;
        ctx.stroke();
        ctx.restore();

        // Dice Face
        let faceVal = this.diceRoll;
        if (this.isRolling) {
            faceVal = Math.floor(Math.random() * 6) + 1;
        }

        if (faceVal) {
            this.drawDiceDots(ctx, d.x, d.y, d.w, faceVal);
        } else {
            ctx.font = 'bold 11px Inter, sans-serif';
            ctx.fillStyle = '#CBD5E1';
            ctx.textAlign = 'center';
            ctx.fillText(curr.isAi ? 'THINKING' : 'ROLL', d.x + d.w / 2, d.y + d.h / 2 + 4);
        }
    }

    drawDiceDots(ctx, x, y, size, value) {
        ctx.fillStyle = '#FFFFFF';
        const r = 3.5;
        const c1 = x + size * 0.28;
        const c2 = x + size * 0.5;
        const c3 = x + size * 0.72;
        const r1 = y + size * 0.28;
        const r2 = y + size * 0.5;
        const r3 = y + size * 0.72;

        const drawDot = (dx, dy) => {
            ctx.beginPath();
            ctx.arc(dx, dy, r, 0, Math.PI * 2);
            ctx.fill();
        };

        if (value === 1) {
            drawDot(c2, r2);
        } else if (value === 2) {
            drawDot(c1, r1);
            drawDot(c3, r3);
        } else if (value === 3) {
            drawDot(c1, r1);
            drawDot(c2, r2);
            drawDot(c3, r3);
        } else if (value === 4) {
            drawDot(c1, r1);
            drawDot(c3, r1);
            drawDot(c1, r3);
            drawDot(c3, r3);
        } else if (value === 5) {
            drawDot(c1, r1);
            drawDot(c3, r1);
            drawDot(c2, r2);
            drawDot(c1, r3);
            drawDot(c3, r3);
        } else if (value === 6) {
            drawDot(c1, r1);
            drawDot(c3, r1);
            drawDot(c1, r2);
            drawDot(c3, r2);
            drawDot(c1, r3);
            drawDot(c3, r3);
        }
    }
}

window.LudoGame = LudoGame;
