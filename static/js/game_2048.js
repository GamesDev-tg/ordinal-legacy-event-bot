/**
 * Ordinal Legacy - 2048 Satoshis
 * 4x4 sliding merge puzzle with touch swipes, arrow controls, and glowing Satoshi tiles.
 */
class Game2048 {
    constructor(canvas, onGameOver) {
        this.canvas = canvas;
        this.ctx = canvas.getContext('2d');
        this.onGameOver = onGameOver;
        this.running = false;
        this.startTime = 0;
        this.size = 4;
        this.grid = [];
        this.score = 0;
        this.gameOver = false;
        this.touchStartX = 0;
        this.touchStartY = 0;

        this.handleKeyDown = this.handleKeyDown.bind(this);
        this.handleTouchStart = this.handleTouchStart.bind(this);
        this.handleTouchEnd = this.handleTouchEnd.bind(this);
        this.handleClick = this.handleClick.bind(this);
    }

    start() {
        this.running = true;
        this.startTime = Date.now();
        this.initGrid();
        window.addEventListener('keydown', this.handleKeyDown);
        this.canvas.addEventListener('touchstart', this.handleTouchStart, { passive: false });
        this.canvas.addEventListener('touchend', this.handleTouchEnd, { passive: false });
        this.canvas.addEventListener('click', this.handleClick);
        this.animate = this.animate.bind(this);
        requestAnimationFrame(this.animate);
    }

    stop() {
        this.running = false;
        window.removeEventListener('keydown', this.handleKeyDown);
        this.canvas.removeEventListener('touchstart', this.handleTouchStart);
        this.canvas.removeEventListener('touchend', this.handleTouchEnd);
        this.canvas.removeEventListener('click', this.handleClick);
    }

    initGrid() {
        this.grid = Array.from({ length: this.size }, () => Array(this.size).fill(0));
        this.score = 0;
        this.gameOver = false;
        this.spawnTile();
        this.spawnTile();
    }

    spawnTile() {
        const empties = [];
        for (let r = 0; r < this.size; r++) {
            for (let c = 0; c < this.size; c++) {
                if (this.grid[r][c] === 0) empties.push({ r, c });
            }
        }
        if (empties.length > 0) {
            const spot = empties[Math.floor(Math.random() * empties.length)];
            this.grid[spot.r][spot.c] = Math.random() < 0.1 ? 4 : 2;
        }
    }

    handleKeyDown(e) {
        if (!this.running || this.gameOver) return;
        if (['ArrowUp', 'KeyW'].includes(e.code)) {
            e.preventDefault();
            this.move('up');
        } else if (['ArrowDown', 'KeyS'].includes(e.code)) {
            e.preventDefault();
            this.move('down');
        } else if (['ArrowLeft', 'KeyA'].includes(e.code)) {
            e.preventDefault();
            this.move('left');
        } else if (['ArrowRight', 'KeyD'].includes(e.code)) {
            e.preventDefault();
            this.move('right');
        }
    }

    handleTouchStart(e) {
        if (e.touches && e.touches[0]) {
            this.touchStartX = e.touches[0].clientX;
            this.touchStartY = e.touches[0].clientY;
        }
    }

    handleTouchEnd(e) {
        if (!e.changedTouches || !e.changedTouches[0] || this.gameOver) return;
        const dx = e.changedTouches[0].clientX - this.touchStartX;
        const dy = e.changedTouches[0].clientY - this.touchStartY;
        const absX = Math.abs(dx);
        const absY = Math.abs(dy);

        if (Math.max(absX, absY) > 25) {
            if (absX > absY) {
                this.move(dx > 0 ? 'right' : 'left');
            } else {
                this.move(dy > 0 ? 'down' : 'up');
            }
        }
    }

    handleClick(e) {
        const rect = this.canvas.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;

        // Virtual Arrow Pads at the bottom
        const padY = this.canvas.height - 85;
        const cx = this.canvas.width / 2;

        if (Math.hypot(x - cx, y - (padY - 25)) < 22) this.move('up');
        else if (Math.hypot(x - cx, y - (padY + 25)) < 22) this.move('down');
        else if (Math.hypot(x - (cx - 45), y - padY) < 22) this.move('left');
        else if (Math.hypot(x - (cx + 45), y - padY) < 22) this.move('right');
    }

    move(dir) {
        if (this.gameOver) return;

        const prevGrid = JSON.stringify(this.grid);
        let moved = false;

        const slideRow = (row) => {
            let filtered = row.filter(x => x !== 0);
            for (let i = 0; i < filtered.length - 1; i++) {
                if (filtered[i] === filtered[i + 1]) {
                    filtered[i] *= 2;
                    this.score += filtered[i];
                    filtered.splice(i + 1, 1);
                }
            }
            while (filtered.length < this.size) filtered.push(0);
            return filtered;
        };

        if (dir === 'left') {
            for (let r = 0; r < this.size; r++) {
                this.grid[r] = slideRow(this.grid[r]);
            }
        } else if (dir === 'right') {
            for (let r = 0; r < this.size; r++) {
                this.grid[r] = slideRow(this.grid[r].reverse()).reverse();
            }
        } else if (dir === 'up') {
            for (let c = 0; c < this.size; c++) {
                let col = [this.grid[0][c], this.grid[1][c], this.grid[2][c], this.grid[3][c]];
                col = slideRow(col);
                for (let r = 0; r < this.size; r++) this.grid[r][c] = col[r];
            }
        } else if (dir === 'down') {
            for (let c = 0; c < this.size; c++) {
                let col = [this.grid[3][c], this.grid[2][c], this.grid[1][c], this.grid[0][c]];
                col = slideRow(col);
                for (let r = 0; r < this.size; r++) this.grid[3 - r][c] = col[r];
            }
        }

        if (JSON.stringify(this.grid) !== prevGrid) {
            this.spawnTile();
            if (this.checkGameOver()) {
                this.gameOver = true;
                const duration = Date.now() - this.startTime;
                const pts = this.score >= 2048 ? 3 : (this.score >= 500 ? 2 : 1);
                setTimeout(() => {
                    if (this.onGameOver) this.onGameOver(pts, Math.max(3500, duration));
                }, 1400);
            }
        }
    }

    checkGameOver() {
        for (let r = 0; r < this.size; r++) {
            for (let c = 0; c < this.size; c++) {
                if (this.grid[r][c] === 0) return false;
                if (c + 1 < this.size && this.grid[r][c] === this.grid[r][c + 1]) return false;
                if (r + 1 < this.size && this.grid[r][c] === this.grid[r + 1][c]) return false;
            }
        }
        return true;
    }

    getGridBounds() {
        const w = this.canvas.width;
        const gridW = Math.min(w - 32, 330);
        const cellW = (gridW - 30) / 4;
        return {
            x: (w - gridW) / 2,
            y: 75,
            w: gridW,
            h: gridW,
            cellW: cellW
        };
    }

    getTileStyle(val) {
        const styles = {
            2: { bg: '#1E293B', text: '#F8FAFC', label: '2 Sats' },
            4: { bg: '#0369A1', text: '#E0F2FE', label: '4 Sats' },
            8: { bg: '#0D9488', text: '#CCFBF1', label: '8 Sats' },
            16: { bg: '#059669', text: '#D1FAE5', label: '16 Sats' },
            32: { bg: '#D97706', text: '#FEF3C7', label: '32 Sats' },
            64: { bg: '#EA580C', text: '#FFEDD5', label: '64 Sats' },
            128: { bg: '#E11D48', text: '#FFE4E6', label: '128 Sats' },
            256: { bg: '#7C3AED', text: '#EDE9FE', label: '256 Sats' },
            512: { bg: '#4F46E5', text: '#EEF2FF', label: '512 Sats' },
            1024: { bg: '#B45309', text: '#FEF08A', label: '1K Sats' },
            2048: { bg: '#F59E0B', text: '#1E1B4B', label: '₿ SATOSHI' },
            4096: { bg: '#831843', text: '#FCE7F3', label: 'GENESIS' }
        };
        return styles[val] || { bg: '#0F172A', text: '#94A3B8', label: String(val) };
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

        // Header
        ctx.font = 'bold 15px Inter, sans-serif';
        ctx.fillStyle = '#F59E0B';
        ctx.textAlign = 'center';
        ctx.fillText('⚡ 2048 SATOSHIS ARCADE ⚡', w / 2, 28);

        ctx.font = '12px Inter, sans-serif';
        ctx.fillStyle = '#94A3B8';
        ctx.fillText(`Score: ${this.score.toLocaleString()} | Slide to merge matching sats`, w / 2, 50);

        const b = this.getGridBounds();

        // Background Board
        ctx.fillStyle = '#0B0F17';
        ctx.beginPath();
        ctx.roundRect(b.x, b.y, b.w, b.h, 14);
        ctx.fill();
        ctx.strokeStyle = '#1E293B';
        ctx.lineWidth = 3;
        ctx.stroke();

        // Render Tiles
        const gap = 8;
        const pad = 8;
        for (let r = 0; r < 4; r++) {
            for (let c = 0; c < 4; c++) {
                const tx = b.x + pad + c * (b.cellW + gap);
                const ty = b.y + pad + r * (b.cellW + gap);
                const val = this.grid[r][c];

                if (val === 0) {
                    ctx.fillStyle = '#111827';
                    ctx.beginPath();
                    ctx.roundRect(tx, ty, b.cellW, b.cellW, 8);
                    ctx.fill();
                } else {
                    const st = this.getTileStyle(val);
                    ctx.save();
                    if (val >= 256) {
                        ctx.shadowColor = st.bg;
                        ctx.shadowBlur = 12;
                    }
                    ctx.fillStyle = st.bg;
                    ctx.beginPath();
                    ctx.roundRect(tx, ty, b.cellW, b.cellW, 8);
                    ctx.fill();
                    ctx.restore();

                    ctx.font = val >= 1024 ? 'bold 10px Inter, sans-serif' : 'bold 14px Inter, sans-serif';
                    ctx.fillStyle = st.text;
                    ctx.textAlign = 'center';
                    ctx.fillText(st.label, tx + b.cellW / 2, ty + b.cellW / 2 + 5);
                }
            }
        }

        // On-Screen Arrow Directional Pads
        const padY = h - 85;
        const cx = w / 2;
        const drawPadBtn = (bx, by, symbol) => {
            ctx.beginPath();
            ctx.arc(bx, by, 18, 0, Math.PI * 2);
            ctx.fillStyle = '#1E293B';
            ctx.fill();
            ctx.strokeStyle = '#334155';
            ctx.lineWidth = 1.5;
            ctx.stroke();

            ctx.font = '14px sans-serif';
            ctx.fillStyle = '#F8FAFC';
            ctx.textAlign = 'center';
            ctx.fillText(symbol, bx, by + 5);
        };

        drawPadBtn(cx, padY - 26, '▲');
        drawPadBtn(cx, padY + 26, '▼');
        drawPadBtn(cx - 45, padY, '◀');
        drawPadBtn(cx + 45, padY, '▶');
    }
}

window.Game2048 = Game2048;
