class RangoliGame {
    constructor(canvas, onGameOver) {
        this.canvas = canvas;
        this.ctx = canvas.getContext('2d');
        this.onGameOver = onGameOver;
        this.running = false;
        this.startTime = 0;
        this.playStartTime = 0;
        this.sequence = [];
        this.playerStep = 0;
        this.activePetal = -1;
        this.state = 'showing';
        this.errors = 0;
        this.score = 1;
        this.timeoutTimer = null;

        // Exact GDD Specs:
        // Petal 1: Kumkum Red (Note C4, Distinct Diamond Symbol ◆)
        // Petal 2: Haldi Gold (Note E4, Distinct Circle Symbol ●)
        // Petal 3: Peacock Blue (Note G4, Distinct Hexagon Symbol ⬡)
        // Petal 4: Marigold Orange (Note B4, Distinct Triangle Symbol ▲)
        this.petals = [
            { id: 0, name: 'Kumkum Red', color: '#DC2626', activeColor: '#F87171', glow: '#EF4444', symbol: '◆', angle: -Math.PI / 2 },
            { id: 1, name: 'Haldi Gold', color: '#D97706', activeColor: '#FDE047', glow: '#FBBF24', symbol: '●', angle: 0 },
            { id: 2, name: 'Peacock Blue', color: '#0284C7', activeColor: '#7DD3FC', glow: '#38BDF8', symbol: '⬡', angle: Math.PI / 2 },
            { id: 3, name: 'Marigold Orange', color: '#EA580C', activeColor: '#FDBA74', glow: '#FB923C', symbol: '▲', angle: Math.PI }
        ];

        this.handleClick = this.handleClick.bind(this);
    }

    start() {
        this.running = true;
        this.startTime = Date.now();
        // 5-step sequence within 4-to-6 step GDD specification
        this.sequence = [
            Math.floor(Math.random() * 4),
            Math.floor(Math.random() * 4),
            Math.floor(Math.random() * 4),
            Math.floor(Math.random() * 4),
            Math.floor(Math.random() * 4)
        ];
        this.playerStep = 0;
        this.errors = 0;
        this.state = 'showing';
        this.canvas.addEventListener('click', this.handleClick);
        this.canvas.addEventListener('touchstart', this.handleClick, { passive: false });
        this.playSequence();
        this.animate = this.animate.bind(this);
        requestAnimationFrame(this.animate);
    }

    stop() {
        this.running = false;
        if (this.timeoutTimer) clearTimeout(this.timeoutTimer);
        this.canvas.removeEventListener('click', this.handleClick);
        this.canvas.removeEventListener('touchstart', this.handleClick);
    }

    async playSequence() {
        await new Promise(r => setTimeout(r, 600));
        for (let i = 0; i < this.sequence.length; i++) {
            if (!this.running) return;
            this.activePetal = this.sequence[i];
            window.festivalAudio?.playRangoliNote(this.activePetal);
            if (window.Telegram?.WebApp?.HapticFeedback) {
                window.Telegram.WebApp.HapticFeedback.impactOccurred('light');
            }
            // 400ms flash duration
            await new Promise(r => setTimeout(r, 400));
            this.activePetal = -1;
            // 200ms pause
            await new Promise(r => setTimeout(r, 200));
        }
        if (!this.running) return;
        this.state = 'playing';
        this.playStartTime = Date.now();

        // 9-second maximum window (6s flawless + 3s grace)
        this.timeoutTimer = setTimeout(() => {
            if (this.running && this.state === 'playing') {
                this.state = 'done';
                this.finishRound(true);
            }
        }, 9000);
    }

    handleClick(e) {
        if (!this.running || this.state !== 'playing') return;
        if (Date.now() - (this.lastClickTime || 0) < 250) return;
        this.lastClickTime = Date.now();
        if (e && e.preventDefault && e.type === 'touchstart') e.preventDefault();

        const rect = this.canvas.getBoundingClientRect();
        const clientX = e.touches ? e.touches[0].clientX : e.clientX;
        const clientY = e.touches ? e.touches[0].clientY : e.clientY;
        const x = (clientX - rect.left) * (this.canvas.width / rect.width);
        const y = (clientY - rect.top) * (this.canvas.height / rect.height);
        const cx = this.canvas.width / 2;
        const cy = this.canvas.height / 2 - 25;
        const r = Math.min(this.canvas.width, this.canvas.height) * 0.32;

        let closestPetal = -1;
        let minDist = 99999;

        this.petals.forEach((p, idx) => {
            const px = cx + Math.cos(p.angle) * r;
            const py = cy + Math.sin(p.angle) * r;
            const dist = Math.hypot(x - px, y - py);
            if (dist < minDist && dist < r * 0.55) {
                minDist = dist;
                closestPetal = idx;
            }
        });

        if (closestPetal === -1) return;

        this.activePetal = closestPetal;
        window.festivalAudio?.playRangoliNote(closestPetal);
        if (window.Telegram?.WebApp?.HapticFeedback) {
            window.Telegram.WebApp.HapticFeedback.impactOccurred('light');
        }
        setTimeout(() => { this.activePetal = -1; }, 200);

        if (closestPetal === this.sequence[this.playerStep]) {
            this.playerStep++;
            if (this.playerStep === this.sequence.length) {
                if (this.timeoutTimer) clearTimeout(this.timeoutTimer);
                this.state = 'done';
                this.finishRound(false);
            }
        } else {
            this.errors++;
            if (this.errors >= 2) {
                if (this.timeoutTimer) clearTimeout(this.timeoutTimer);
                this.state = 'done';
                this.finishRound(false);
            }
        }
    }

    finishRound(timedOut) {
        const solveTimeSec = (Date.now() - this.playStartTime) / 1000.0;

        // Blueprint Scoring:
        // - Flawless sequence within 6 seconds -> 3 Points -> notificationOccurred('success')
        // - Completed within +3s grace window (<= 9s) or with 1 corrected mistake -> 2 Points -> impactOccurred('medium')
        // - >= 50% sequence entered before timeout -> 1 Point -> impactOccurred('light')
        if (this.playerStep === this.sequence.length && this.errors === 0 && solveTimeSec <= 6.0) {
            this.score = 3;
            if (window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred) {
                window.Telegram.WebApp.HapticFeedback.notificationOccurred('success');
            }
            window.festivalAudio?.playSuccessChime();
        } else if (this.playerStep === this.sequence.length && (this.errors <= 1 || solveTimeSec <= 9.0)) {
            this.score = 2;
            if (window.Telegram?.WebApp?.HapticFeedback) {
                window.Telegram.WebApp.HapticFeedback.impactOccurred('medium');
            }
            window.festivalAudio?.playDholBeat();
        } else if (this.playerStep >= Math.ceil(this.sequence.length * 0.5)) {
            this.score = 1;
            if (window.Telegram?.WebApp?.HapticFeedback) {
                window.Telegram.WebApp.HapticFeedback.impactOccurred('light');
            }
            window.festivalAudio?.playFountainSizzle();
        } else {
            this.score = 1;
            if (window.Telegram?.WebApp?.HapticFeedback) {
                window.Telegram.WebApp.HapticFeedback.impactOccurred('light');
            }
        }

        setTimeout(() => {
            this.stop();
            this.onGameOver(this.score, Math.max(3200, Date.now() - this.startTime));
        }, 1500);
    }

    drawLotusPetal(cx, cy, angle, length, width, fillStyle, strokeStyle, lineWidth = 2) {
        const ctx = this.ctx;
        ctx.save();
        ctx.translate(cx, cy);
        ctx.rotate(angle);

        ctx.beginPath();
        ctx.moveTo(0, 0);
        ctx.bezierCurveTo(width / 2, length * 0.4, width / 2, length * 0.8, 0, length);
        ctx.bezierCurveTo(-width / 2, length * 0.8, -width / 2, length * 0.4, 0, 0);
        ctx.closePath();

        ctx.fillStyle = fillStyle;
        ctx.fill();
        ctx.lineWidth = lineWidth;
        ctx.strokeStyle = strokeStyle;
        ctx.stroke();
        ctx.restore();
    }

    animate() {
        if (!this.running) return;
        const w = this.canvas.width;
        const h = this.canvas.height;
        const ctx = this.ctx;

        // Sacred dark marble flooring
        ctx.fillStyle = '#0B0D14';
        ctx.fillRect(0, 0, w, h);

        // Marble grain texture
        ctx.save();
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.03)';
        ctx.lineWidth = 1;
        for (let i = 0; i < 4; i++) {
            ctx.beginPath();
            ctx.moveTo(0, (i + 1) * (h / 5));
            ctx.bezierCurveTo(w * 0.3, (i + 1) * (h / 5) - 30, w * 0.7, (i + 1) * (h / 5) + 30, w, (i + 1) * (h / 5));
            ctx.stroke();
        }
        ctx.restore();

        const cx = w / 2;
        const cy = h / 2 - 25;
        const r = Math.min(w, h) * 0.32;

        // Concentric Gold Rangoli Mandalas
        ctx.beginPath();
        ctx.arc(cx, cy, r * 1.35, 0, Math.PI * 2);
        ctx.strokeStyle = 'rgba(245, 158, 11, 0.15)';
        ctx.lineWidth = 2;
        ctx.stroke();

        ctx.beginPath();
        ctx.arc(cx, cy, r * 0.75, 0, Math.PI * 2);
        ctx.strokeStyle = 'rgba(245, 158, 11, 0.25)';
        ctx.lineWidth = 2;
        ctx.stroke();

        // 8-Petal Lotus Symmetry: 4 Intermediate Decorative Petals (Diagonals)
        for (let i = 0; i < 4; i++) {
            const diagAngle = -Math.PI / 4 + i * (Math.PI / 2);
            this.drawLotusPetal(cx, cy, diagAngle, r * 1.05, r * 0.42, '#1E293B', '#F59E0B', 1.5);
            // Rangoli white rice dots
            const dotX = cx + Math.cos(diagAngle) * (r * 1.15);
            const dotY = cy + Math.sin(diagAngle) * (r * 1.15);
            ctx.beginPath();
            ctx.arc(dotX, dotY, 3, 0, Math.PI * 2);
            ctx.fillStyle = '#FDE047';
            ctx.fill();
        }

        // 4 Primary Interactive Lotus Petals (North, East, South, West)
        this.petals.forEach((p, idx) => {
            const isActive = (this.activePetal === idx);
            const px = cx + Math.cos(p.angle) * r;
            const py = cy + Math.sin(p.angle) * r;

            // Draw primary petal shape
            this.drawLotusPetal(
                cx, cy, p.angle, r * 1.15, r * 0.52,
                isActive ? p.activeColor : p.color,
                isActive ? '#FFFFFF' : '#F59E0B',
                isActive ? 4 : 2
            );

            // Sacred Rangoli Emblem Token
            ctx.save();
            if (isActive) {
                ctx.shadowColor = p.glow;
                ctx.shadowBlur = 24;
            }
            ctx.beginPath();
            ctx.arc(px, py, r * 0.25, 0, Math.PI * 2);
            ctx.fillStyle = isActive ? '#FFFFFF' : 'rgba(15, 23, 42, 0.85)';
            ctx.fill();
            ctx.lineWidth = isActive ? 3 : 2;
            ctx.strokeStyle = isActive ? p.glow : '#F59E0B';
            ctx.stroke();

            // Distinct geometric symbols (◆, ●, ⬡, ▲)
            ctx.font = 'bold 22px sans-serif';
            ctx.fillStyle = isActive ? p.color : '#F8FAFC';
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillText(p.symbol, px, py);
            ctx.restore();
        });

        // Center Akhand Diya Core
        ctx.save();
        ctx.shadowColor = '#F59E0B';
        ctx.shadowBlur = 18;
        ctx.beginPath();
        ctx.arc(cx, cy, 26, 0, Math.PI * 2);
        ctx.fillStyle = '#78350F';
        ctx.fill();
        ctx.lineWidth = 3;
        ctx.strokeStyle = '#FDE047';
        ctx.stroke();

        ctx.font = '28px sans-serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText('🪔', cx, cy);
        ctx.restore();

        // Footer Feedback & Timer Display
        ctx.textAlign = 'center';
        if (this.state === 'showing') {
            ctx.font = 'bold 15px sans-serif';
            ctx.fillStyle = '#F59E0B';
            ctx.fillText('✨ Memorize the Lotus Petal Harmony...', cx, h - 35);
        } else if (this.state === 'playing') {
            const timeElapsed = (Date.now() - this.playStartTime) / 1000.0;
            const remainingSec = Math.max(0, 6.0 - timeElapsed);
            ctx.font = 'bold 15px sans-serif';
            ctx.fillStyle = remainingSec > 0 ? '#10B981' : '#F59E0B';
            ctx.fillText(`Reproduce Harmony: Step ${this.playerStep + 1}/${this.sequence.length} (${remainingSec.toFixed(1)}s for 3 Pts)`, cx, h - 35);
        } else {
            ctx.font = 'bold 22px sans-serif';
            ctx.fillStyle = this.score === 3 ? '#10B981' : (this.score === 2 ? '#F59E0B' : '#94A3B8');
            const resText = this.score === 3 ? '🌸 FLAWLESS HARMONY! (+3 Sparks)' : (this.score === 2 ? '✨ SACRED RANGOLI! (+2 Sparks)' : '🪔 BASE OFFERING (+1 Spark)');
            ctx.fillText(resText, cx, h - 35);
        }

        requestAnimationFrame(this.animate);
    }
}
window.RangoliGame = RangoliGame;
