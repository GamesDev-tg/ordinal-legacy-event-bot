class ChakriGame {
    constructor(canvas, onGameOver) {
        this.canvas = canvas;
        this.ctx = canvas.getContext('2d');
        this.onGameOver = onGameOver;
        this.running = false;
        this.startTime = 0;
        this.angle = 0;
        this.speed = 0.065;  // Increased from 0.048 for faster, more exciting spin
        this.ignited = false;
        this.score = 1;
        this.particles = [];
        this.sparks = [];
        // Exact Blueprint specs:
        // Golden Deepak Zone: 12% arc width (43.2 deg = 0.24 * PI)
        // Silver Halo Zone: 20% arc width (72.0 deg = 0.40 * PI total, 0.20 * PI each flank)
        this.targetStart = Math.PI * 0.75;
        this.targetWidth = Math.PI * 0.24;
        this.silverMargin = Math.PI * 0.20;

        this.handleCanvasTap = this.handleCanvasTap.bind(this);
    }

    start() {
        this.running = true;
        this.startTime = Date.now();
        this.angle = 0;
        this.ignited = false;
        this.particles = [];
        this.sparks = [];
        this.score = 1;
        this.canvas.addEventListener('click', this.handleCanvasTap);
        this.canvas.addEventListener('touchstart', this.handleCanvasTap, { passive: false });
        this.animate = this.animate.bind(this);
        requestAnimationFrame(this.animate);
    }

    stop() {
        this.running = false;
        this.canvas.removeEventListener('click', this.handleCanvasTap);
        this.canvas.removeEventListener('touchstart', this.handleCanvasTap);
    }

    handleCanvasTap(e) {
        if (e && e.preventDefault && e.type === 'touchstart') e.preventDefault();
        this.handleTap();
    }

    handleTap() {
        if (!this.running || this.ignited) return;
        if (Date.now() - (this.lastTapTime || 0) < 400) return;
        this.lastTapTime = Date.now();
        this.ignited = true;
        
        const norm = this.angle % (Math.PI * 2);
        const targetEnd = this.targetStart + this.targetWidth;
        const silverStart = this.targetStart - this.silverMargin;
        const silverEnd = targetEnd + this.silverMargin;
        
        if (norm >= this.targetStart && norm <= targetEnd) {
            this.score = 3;
            if (window.Telegram?.WebApp?.HapticFeedback) {
                window.Telegram.WebApp.HapticFeedback.impactOccurred('heavy');
            }
            window.festivalAudio?.playAerialMultiBurst();
        } else if (norm >= silverStart && norm <= silverEnd) {
            this.score = 2;
            if (window.Telegram?.WebApp?.HapticFeedback) {
                window.Telegram.WebApp.HapticFeedback.impactOccurred('medium');
            }
            window.festivalAudio?.playSilverShower();
        } else {
            this.score = 1;
            if (window.Telegram?.WebApp?.HapticFeedback) {
                window.Telegram.WebApp.HapticFeedback.impactOccurred('light');
            }
            window.festivalAudio?.playFountainSizzle();
        }

        const cx = this.canvas.width / 2;
        const cy = this.canvas.height / 2 - 20;
        this.spawnBurst(cx, cy, this.score);

        // Responsive festive burst celebration
        setTimeout(() => {
            this.stop();
            this.onGameOver(this.score, Math.max(3200, Date.now() - this.startTime));
        }, 1800);
    }

    spawnBurst(x, y, tier) {
        const count = tier === 3 ? 90 : (tier === 2 ? 50 : 25);
        const colors = tier === 3 
            ? ['#F59E0B', '#EF4444', '#10B981', '#3B82F6', '#FBBF24', '#FFFFFF'] 
            : (tier === 2 ? ['#E2E8F0', '#94A3B8', '#F59E0B', '#CBD5E1'] : ['#F97316', '#EA580C', '#78350F']);
        
        for (let i = 0; i < count; i++) {
            const spd = Math.random() * (tier === 3 ? 8 : 5) + 2;
            const dir = Math.random() * Math.PI * 2;
            this.particles.push({
                x, y,
                vx: Math.cos(dir) * spd,
                vy: Math.sin(dir) * spd,
                color: colors[Math.floor(Math.random() * colors.length)],
                size: Math.random() * 4 + 2,
                life: 1.0,
                decay: Math.random() * 0.015 + 0.01
            });
        }
    }

    animate() {
        if (!this.running) return;
        const w = this.canvas.width;
        const h = this.canvas.height;
        const ctx = this.ctx;

        // Dark festival sky background
        ctx.fillStyle = '#0B0F19';
        ctx.fillRect(0, 0, w, h);

        const cx = w / 2;
        const cy = h / 2 - 25;
        const radius = Math.min(w, h) * 0.33;

        // Track outer glow
        ctx.save();
        ctx.shadowColor = 'rgba(245, 158, 11, 0.2)';
        ctx.shadowBlur = 12;

        // Base 360 ring (Outer zone - 68%)
        ctx.beginPath();
        ctx.arc(cx, cy, radius, 0, Math.PI * 2);
        ctx.lineWidth = 14;
        ctx.strokeStyle = '#1E293B';
        ctx.stroke();

        // Silver Halo Zone (20% arc width)
        ctx.beginPath();
        ctx.arc(cx, cy, radius, this.targetStart - this.silverMargin, this.targetStart + this.targetWidth + this.silverMargin);
        ctx.lineWidth = 15;
        ctx.strokeStyle = '#94A3B8';
        ctx.stroke();

        // Golden Deepak Zone (12% arc width)
        ctx.beginPath();
        ctx.arc(cx, cy, radius, this.targetStart, this.targetStart + this.targetWidth);
        ctx.lineWidth = 18;
        ctx.strokeStyle = '#F59E0B';
        ctx.stroke();
        ctx.restore();

        // Target markers & labels
        const markAngle = this.targetStart + this.targetWidth / 2;
        const mx = cx + Math.cos(markAngle) * (radius + 24);
        const my = cy + Math.sin(markAngle) * (radius + 24);
        ctx.font = 'bold 12px sans-serif';
        ctx.fillStyle = '#FBBF24';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText('⭐ 3 PTS', mx, my);

        // Ground spinning chakri particles
        if (!this.ignited) {
            this.angle += this.speed;
            if (Math.random() < 0.6) {
                const sparkDir = this.angle + (Math.random() - 0.5) * 0.8;
                this.sparks.push({
                    x: cx + Math.cos(this.angle) * radius,
                    y: cy + Math.sin(this.angle) * radius,
                    vx: Math.cos(sparkDir) * (Math.random() * 3 + 1),
                    vy: Math.sin(sparkDir) * (Math.random() * 3 + 1),
                    life: 1.0,
                    color: Math.random() < 0.5 ? '#FDE047' : '#F97316'
                });
            }
        }

        // Render tangential sparks
        for (let i = this.sparks.length - 1; i >= 0; i--) {
            const spk = this.sparks[i];
            spk.x += spk.vx;
            spk.y += spk.vy;
            spk.life -= 0.05;
            if (spk.life <= 0) {
                this.sparks.splice(i, 1);
                continue;
            }
            ctx.beginPath();
            ctx.arc(spk.x, spk.y, 2 * spk.life, 0, Math.PI * 2);
            ctx.fillStyle = spk.color;
            ctx.fill();
        }

        // Rotating Chakri Flame Runner
        const px = cx + Math.cos(this.angle) * radius;
        const py = cy + Math.sin(this.angle) * radius;

        ctx.save();
        ctx.shadowColor = '#F59E0B';
        ctx.shadowBlur = 18;
        ctx.beginPath();
        ctx.arc(px, py, 11, 0, Math.PI * 2);
        ctx.fillStyle = '#EA580C';
        ctx.fill();
        ctx.lineWidth = 3;
        ctx.strokeStyle = '#FDE047';
        ctx.stroke();
        ctx.restore();

        // Center Divine Diya
        ctx.font = '44px sans-serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText('🪔', cx, cy);

        // Continuous festive fireworks after ignition
        if (this.ignited && Math.random() < 0.18) {
            const bx = cx + (Math.random() - 0.5) * (w * 0.7);
            const by = cy - 40 + (Math.random() - 0.5) * (h * 0.4);
            this.spawnBurst(bx, by, this.score);
        }

        // Render explosion burst particles
        for (let i = this.particles.length - 1; i >= 0; i--) {
            const p = this.particles[i];
            p.x += p.vx;
            p.y += p.vy;
            p.vy += 0.08; // subtle gravity
            p.life -= p.decay;
            if (p.life <= 0) {
                this.particles.splice(i, 1);
                continue;
            }
            ctx.beginPath();
            ctx.arc(p.x, p.y, p.size * p.life, 0, Math.PI * 2);
            ctx.fillStyle = p.color;
            ctx.fill();
        }

        // Instructions or result banner
        ctx.textAlign = 'center';
        if (!this.ignited) {
            ctx.font = '15px sans-serif';
            ctx.fillStyle = '#94A3B8';
            ctx.fillText('Tap IGNITE when flame hits the Golden Zone!', cx, h - 35);
        } else {
            ctx.font = 'bold 22px sans-serif';
            ctx.fillStyle = this.score === 3 ? '#10B981' : (this.score === 2 ? '#F59E0B' : '#94A3B8');
            const title = this.score === 3 ? '🌟 GOLDEN BLAST! (+3 Sparks)' : (this.score === 2 ? '✨ SILVER SHOWER! (+2 Sparks)' : '🪔 BASE RUN (+1 Spark)');
            ctx.fillText(title, cx, h - 35);
        }

        requestAnimationFrame(this.animate.bind(this));
    }
}
window.ChakriGame = ChakriGame;
