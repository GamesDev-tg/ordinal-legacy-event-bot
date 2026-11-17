/**
 * Ordinal Legacy - Connect 4 (Gravity 4-in-a-Row)
 * Interactive HTML5 Canvas Connect 4 with AI opponent, drop physics, and neon glow.
 */
class Connect4Game {
    constructor(canvas, onGameOver) {
        this.canvas = canvas;
        this.ctx = canvas.getContext('2d');
        this.onGameOver = onGameOver;
        this.running = false;
        this.startTime = 0;
        this.cols = 7;
        this.rows = 6;
        this.board = [];
        this.turn = 1; // 1 = Player (Red), 2 = AI (Yellow)
        this.gameOver = false;
        this.winner = 0;
        this.fallingPieces = [];
        this.winningLine = null;

        this.handleCanvasClick = this.handleCanvasClick.bind(this);
    }

    start() {
        this.running = true;
        this.startTime = Date.now();
        this.initBoard();
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

    initBoard() {
        this.board = Array.from({ length: this.rows }, () => Array(this.cols).fill(0));
        this.turn = 1;
        this.gameOver = false;
        this.winner = 0;
        this.fallingPieces = [];
        this.winningLine = null;
    }

    handleCanvasClick(e) {
        const rect = this.canvas.getBoundingClientRect();
        this.handleClickAt(e.clientX - rect.left, e.clientY - rect.top);
    }

    handleClickAt(x, y) {
        if (!this.running || this.gameOver || this.turn !== 1) return;
        if (this.fallingPieces.length > 0) return;

        const bounds = this.getGridBounds();
        if (x < bounds.x || x > bounds.x + bounds.w || y < bounds.y - 40 || y > bounds.y + bounds.h) return;

        const col = Math.floor((x - bounds.x) / bounds.cellW);
        if (col >= 0 && col < this.cols) {
            this.dropPiece(col, 1);
        }
    }

    dropPiece(col, piece) {
        for (let r = this.rows - 1; r >= 0; r--) {
            if (this.board[r][col] === 0) {
                const bounds = this.getGridBounds();
                const targetX = bounds.x + col * bounds.cellW + bounds.cellW / 2;
                const targetY = bounds.y + r * bounds.cellH + bounds.cellH / 2;

                this.fallingPieces.push({
                    col: col,
                    row: r,
                    piece: piece,
                    x: targetX,
                    y: bounds.y - 20,
                    targetY: targetY,
                    vy: 3
                });

                this.board[r][col] = piece;

                const win = this.checkWin(r, col, piece);
                if (win) {
                    this.gameOver = true;
                    this.winner = piece;
                    this.winningLine = win;
                    const duration = Date.now() - this.startTime;
                    setTimeout(() => {
                        if (this.onGameOver) this.onGameOver(piece === 1 ? 3 : 1, Math.max(3500, duration));
                    }, 1400);
                } else if (this.isBoardFull()) {
                    this.gameOver = true;
                    this.winner = 3; // Tie
                    const duration = Date.now() - this.startTime;
                    setTimeout(() => {
                        if (this.onGameOver) this.onGameOver(2, Math.max(3500, duration));
                    }, 1400);
                } else {
                    this.turn = (piece === 1) ? 2 : 1;
                    if (this.turn === 2 && !this.gameOver) {
                        setTimeout(() => this.aiMove(), 550);
                    }
                }
                return;
            }
        }
    }

    aiMove() {
        if (this.gameOver || !this.running) return;

        const validCols = [];
        for (let c = 0; c < this.cols; c++) {
            if (this.board[0][c] === 0) validCols.push(c);
        }
        if (validCols.length === 0) return;

        // 1. Check if AI can win immediately
        for (const c of validCols) {
            const r = this.getLowestEmptyRow(c);
            this.board[r][c] = 2;
            if (this.checkWin(r, c, 2)) {
                this.board[r][c] = 0;
                this.dropPiece(c, 2);
                return;
            }
            this.board[r][c] = 0;
        }

        // 2. Check if player can win and block
        for (const c of validCols) {
            const r = this.getLowestEmptyRow(c);
            this.board[r][c] = 1;
            if (this.checkWin(r, c, 1)) {
                this.board[r][c] = 0;
                this.dropPiece(c, 2);
                return;
            }
            this.board[r][c] = 0;
        }

        // 3. Center preference (col 3, 2, 4, 1, 5, 0, 6)
        for (const pref of [3, 2, 4, 1, 5, 0, 6]) {
            if (validCols.includes(pref)) {
                this.dropPiece(pref, 2);
                return;
            }
        }

        this.dropPiece(validCols[0], 2);
    }

    getLowestEmptyRow(col) {
        for (let r = this.rows - 1; r >= 0; r--) {
            if (this.board[r][col] === 0) return r;
        }
        return -1;
    }

    checkWin(r, c, piece) {
        const directions = [
            [[0, 1], [0, -1]], // Horizontal
            [[1, 0], [-1, 0]], // Vertical
            [[1, 1], [-1, -1]], // Diagonal \
            [[1, -1], [-1, 1]]  // Diagonal /
        ];

        for (const dir of directions) {
            let cells = [[r, c]];
            for (const [dr, dc] of dir) {
                let step = 1;
                while (true) {
                    const nr = r + dr * step;
                    const nc = c + dc * step;
                    if (nr >= 0 && nr < this.rows && nc >= 0 && nc < this.cols && this.board[nr][nc] === piece) {
                        cells.push([nr, nc]);
                        step++;
                    } else {
                        break;
                    }
                }
            }
            if (cells.length >= 4) {
                return cells;
            }
        }
        return null;
    }

    isBoardFull() {
        return this.board[0].every(cell => cell !== 0);
    }

    getGridBounds() {
        const w = this.canvas.width;
        const h = this.canvas.height;
        const gridW = Math.min(w - 24, 380);
        const cellW = gridW / this.cols;
        const cellH = cellW;
        const gridH = cellH * this.rows;
        return {
            x: (w - gridW) / 2,
            y: (h - gridH) / 2 + 10,
            w: gridW,
            h: gridH,
            cellW: cellW,
            cellH: cellH
        };
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

        // Header Title
        ctx.font = 'bold 15px Inter, sans-serif';
        ctx.fillStyle = '#F59E0B';
        ctx.textAlign = 'center';
        ctx.fillText('🔴 CONNECT 4 SHOWDOWN 🟡', w / 2, 28);

        ctx.font = '12px Inter, sans-serif';
        if (this.gameOver) {
            if (this.winner === 1) {
                ctx.fillStyle = '#EF4444';
                ctx.fillText('🎉 YOU CONNECTED 4! VICTORY (+3 Sparks)', w / 2, 50);
            } else if (this.winner === 2) {
                ctx.fillStyle = '#F59E0B';
                ctx.fillText('🤖 AI Connected 4! Better luck next time.', w / 2, 50);
            } else {
                ctx.fillStyle = '#94A3B8';
                ctx.fillText('🤝 Board Full! Perfect Stalemate (+2 Sparks)', w / 2, 50);
            }
        } else {
            ctx.fillStyle = this.turn === 1 ? '#EF4444' : '#F59E0B';
            ctx.fillText(this.turn === 1 ? '🎯 Your Turn (Drop 🔴)' : '🤖 AI is calculating move...', w / 2, 50);
        }

        const b = this.getGridBounds();

        // Draw Blue Grid Plate
        ctx.save();
        ctx.shadowColor = 'rgba(59, 130, 246, 0.4)';
        ctx.shadowBlur = 15;
        ctx.fillStyle = '#1E3A8A';
        ctx.beginPath();
        ctx.roundRect(b.x, b.y, b.w, b.h, 14);
        ctx.fill();
        ctx.strokeStyle = '#3B82F6';
        ctx.lineWidth = 3;
        ctx.stroke();
        ctx.restore();

        // Draw Slots & Stationary Chips
        const radius = b.cellW * 0.38;
        for (let r = 0; r < this.rows; r++) {
            for (let c = 0; c < this.cols; c++) {
                const cx = b.x + c * b.cellW + b.cellW / 2;
                const cy = b.y + r * b.cellH + b.cellH / 2;
                const piece = this.board[r][c];

                // Check if this piece is currently falling
                const isFalling = this.fallingPieces.some(p => p.row === r && p.col === c);

                ctx.beginPath();
                ctx.arc(cx, cy, radius, 0, Math.PI * 2);
                if (piece === 1 && !isFalling) {
                    ctx.fillStyle = '#EF4444';
                    ctx.fill();
                    ctx.strokeStyle = '#FCA5A5';
                    ctx.lineWidth = 2;
                    ctx.stroke();
                } else if (piece === 2 && !isFalling) {
                    ctx.fillStyle = '#F59E0B';
                    ctx.fill();
                    ctx.strokeStyle = '#FDE68A';
                    ctx.lineWidth = 2;
                    ctx.stroke();
                } else {
                    ctx.fillStyle = '#0B0F17';
                    ctx.fill();
                    ctx.strokeStyle = '#1E293B';
                    ctx.lineWidth = 1.5;
                    ctx.stroke();
                }
            }
        }

        // Render Falling Pieces with Physics Lerp
        for (let i = this.fallingPieces.length - 1; i >= 0; i--) {
            const fp = this.fallingPieces[i];
            fp.y += fp.vy;
            fp.vy += 1.8; // gravity

            if (fp.y >= fp.targetY) {
                fp.y = fp.targetY;
                this.fallingPieces.splice(i, 1);
            }

            ctx.beginPath();
            ctx.arc(fp.x, fp.y, radius, 0, Math.PI * 2);
            ctx.fillStyle = fp.piece === 1 ? '#EF4444' : '#F59E0B';
            ctx.fill();
            ctx.strokeStyle = '#FFFFFF';
            ctx.lineWidth = 2;
            ctx.stroke();
        }

        // Draw Winning Laser Beam
        if (this.winningLine) {
            ctx.save();
            ctx.shadowColor = '#FDE68A';
            ctx.shadowBlur = 18;
            ctx.strokeStyle = '#FEF08A';
            ctx.lineWidth = 5;
            ctx.beginPath();
            for (let idx = 0; idx < this.winningLine.length; idx++) {
                const [r, c] = this.winningLine[idx];
                const cx = b.x + c * b.cellW + b.cellW / 2;
                const cy = b.y + r * b.cellH + b.cellH / 2;
                if (idx === 0) ctx.moveTo(cx, cy);
                else ctx.lineTo(cx, cy);
            }
            ctx.stroke();
            ctx.restore();
        }

        // Column Drop Indicators
        if (!this.gameOver && this.turn === 1) {
            for (let c = 0; c < this.cols; c++) {
                if (this.board[0][c] === 0) {
                    const cx = b.x + c * b.cellW + b.cellW / 2;
                    ctx.font = '12px sans-serif';
                    ctx.fillStyle = '#EF4444';
                    ctx.textAlign = 'center';
                    ctx.fillText('▼', cx, b.y - 8);
                }
            }
        }
    }
}

window.Connect4Game = Connect4Game;
