/**
 * Ordinal Legacy - Crypto Wordle (5-Letter Word Clash)
 * Interactive HTML5 Canvas Wordle with on-screen virtual keyboard, touch input, and crypto dictionary.
 */
class WordleGame {
    constructor(canvas, onGameOver) {
        this.canvas = canvas;
        this.ctx = canvas.getContext('2d');
        this.onGameOver = onGameOver;
        this.running = false;
        this.startTime = 0;
        
        this.dictionary = [
            "BLOCK", "MINER", "TOKEN", "CHAIN", "HALVE", "SATOS", "NODES", "FORTH",
            "PROOF", "SHARD", "GUILD", "RUNES", "STAKE", "YIELD", "LEDGER", "FLAME",
            "LIGHT", "SPARK", "POWER", "ASSET", "TRADE", "VAULT", "QUEST", "SMART"
        ];
        this.secret = "BLOCK";
        this.maxGuesses = 6;
        this.wordLen = 5;
        this.guesses = []; // Array of strings e.g. ["MINER", "TOKEN"]
        this.currentInput = "";
        this.gameOver = false;
        this.won = false;

        this.keyStates = {}; // letter -> 'correct', 'present', 'absent'

        this.handleKeyDown = this.handleKeyDown.bind(this);
        this.handleCanvasClick = this.handleCanvasClick.bind(this);
        this.handleTouchStart = this.handleTouchStart.bind(this);
    }

    start() {
        this.running = true;
        this.startTime = Date.now();
        this.initGame();
        window.addEventListener('keydown', this.handleKeyDown);
        this.canvas.addEventListener('click', this.handleCanvasClick);
        this.canvas.addEventListener('touchstart', this.handleTouchStart, { passive: false });
        this.animate = this.animate.bind(this);
        requestAnimationFrame(this.animate);
    }

    stop() {
        this.running = false;
        window.removeEventListener('keydown', this.handleKeyDown);
        this.canvas.removeEventListener('click', this.handleCanvasClick);
        this.canvas.removeEventListener('touchstart', this.handleTouchStart);
    }

    handleTouchStart(e) {
        if (!e.touches || !e.touches[0]) return;
        if (e.cancelable) e.preventDefault();
        const rect = this.canvas.getBoundingClientRect();
        const scaleX = this.canvas.width / rect.width;
        const scaleY = this.canvas.height / rect.height;
        const x = (e.touches[0].clientX - rect.left) * scaleX;
        const y = (e.touches[0].clientY - rect.top) * scaleY;
        this.handleClickAt(x, y);
    }

    handleCanvasClick(e) {
        const rect = this.canvas.getBoundingClientRect();
        const scaleX = this.canvas.width / rect.width;
        const scaleY = this.canvas.height / rect.height;
        const x = (e.clientX - rect.left) * scaleX;
        const y = (e.clientY - rect.top) * scaleY;
        this.handleClickAt(x, y);
    }

    handleTap() {
        // Wired to action button below canvas
        if (this.currentInput.length === 5) {
            this.submitGuess();
        } else {
            this.confirmExit();
        }
    }

    confirmExit() {
        if (!this.running || this.gameOver) return;
        const confirmQuit = window.confirm("Give up on this crypto word and exit? You will still bank 1 Sparks participation bonus.");
        if (confirmQuit) {
            this.gameOver = true;
            this.running = false;
            if (this.onGameOver) {
                const duration = Math.max(3000, Date.now() - this.startTime);
                this.onGameOver(1, duration);
            }
        }
    }

    handleClickAt(x, y) {
        if (!this.running || this.gameOver) return;

        const keyboard = this.getKeyboardLayout();
        for (const row of keyboard) {
            for (const key of row) {
                if (x >= key.x && x <= key.x + key.w && y >= key.y && y <= key.y + key.h) {
                    if (key.label === 'ENTER') {
                        this.submitGuess();
                    } else if (key.label === '⌫') {
                        this.currentInput = this.currentInput.slice(0, -1);
                    } else if (this.currentInput.length < 5) {
                        this.currentInput += key.label;
                    }
                    return;
                }
            }
        }
    }

    submitGuess() {
        if (this.currentInput.length !== 5) return;
        const guess = this.currentInput;
        this.guesses.push(guess);
        this.currentInput = "";

        // Update key states
        const secretArr = this.secret.split('');
        for (let i = 0; i < 5; i++) {
            const ch = guess[i];
            if (ch === secretArr[i]) {
                this.keyStates[ch] = 'correct';
            } else if (secretArr.includes(ch) && this.keyStates[ch] !== 'correct') {
                this.keyStates[ch] = 'present';
            } else if (!this.keyStates[ch]) {
                this.keyStates[ch] = 'absent';
            }
        }

        if (guess === this.secret) {
            this.gameOver = true;
            this.won = true;
            const duration = Date.now() - this.startTime;
            setTimeout(() => {
                if (this.onGameOver) this.onGameOver(3, Math.max(3500, duration));
            }, 1400);
        } else if (this.guesses.length >= this.maxGuesses) {
            this.gameOver = true;
            this.won = false;
            const duration = Date.now() - this.startTime;
            setTimeout(() => {
                if (this.onGameOver) this.onGameOver(1, Math.max(3500, duration));
            }, 1400);
        }
    }

    getGridBounds() {
        const w = this.canvas.width;
        const boxSize = 42;
        const gap = 6;
        const gridW = boxSize * 5 + gap * 4;
        return {
            x: (w - gridW) / 2,
            y: 55,
            boxSize: boxSize,
            gap: gap
        };
    }

    getKeyboardLayout() {
        const w = this.canvas.width;
        const h = this.canvas.height;
        const rows = [
            ['Q', 'W', 'E', 'R', 'T', 'Y', 'U', 'I', 'O', 'P'],
            ['A', 'S', 'D', 'F', 'G', 'H', 'J', 'K', 'L'],
            ['ENTER', 'Z', 'X', 'C', 'V', 'B', 'N', 'M', '⌫']
        ];
        const keyH = 34;
        const gap = 4;
        const startY = h - 130;
        const layout = [];

        for (let r = 0; r < rows.length; r++) {
            const rowKeys = rows[r];
            const isWideRow = (r === 2);
            const standardKeyW = Math.floor((Math.min(w - 16, 360) - gap * 9) / 10);
            const rowW = rowKeys.reduce((acc, k) => acc + (k.length > 1 ? standardKeyW * 1.5 : standardKeyW) + gap, -gap);
            let curX = (w - rowW) / 2;
            const curY = startY + r * (keyH + gap);

            const rowLayout = [];
            for (const label of rowKeys) {
                const kw = (label.length > 1) ? Math.floor(standardKeyW * 1.5) : standardKeyW;
                rowLayout.push({ label, x: curX, y: curY, w: kw, h: keyH });
                curX += kw + gap;
            }
            layout.push(rowLayout);
        }
        return layout;
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
        ctx.fillText('🔤 CRYPTO WORDLE (5 LETTERS) 🔤', w / 2, 26);

        ctx.font = '11px Inter, sans-serif';
        if (this.gameOver) {
            ctx.fillStyle = this.won ? '#10B981' : '#EF4444';
            ctx.fillText(this.won ? `🎉 SOLVED: ${this.secret}! (+3 Sparks)` : `💥 SECRET WAS: ${this.secret} (+1 Spark)`, w / 2, 44);
        } else {
            ctx.fillStyle = '#94A3B8';
            ctx.fillText(`Try ${this.guesses.length + 1}/6 • Guess the 5-letter crypto term`, w / 2, 44);
        }

        // Letter Matrix
        const b = this.getGridBounds();
        for (let r = 0; r < this.maxGuesses; r++) {
            const guess = this.guesses[r];
            const isCurrent = (r === this.guesses.length && !this.gameOver);
            const letters = guess ? guess.split('') : (isCurrent ? this.currentInput.padEnd(5, ' ').split('') : [' ', ' ', ' ', ' ', ' ']);

            for (let c = 0; c < this.wordLen; c++) {
                const bx = b.x + c * (b.boxSize + b.gap);
                const by = b.y + r * (b.boxSize + b.gap);
                const char = letters[c] ? letters[c].trim() : '';

                let bgColor = '#0F172A';
                let borderColor = '#334155';
                let textColor = '#F8FAFC';

                if (guess) {
                    const secretArr = this.secret.split('');
                    if (char === secretArr[c]) {
                        bgColor = '#10B981'; // Green (correct)
                        borderColor = '#34D399';
                    } else if (secretArr.includes(char)) {
                        bgColor = '#D97706'; // Yellow (present)
                        borderColor = '#FBBF24';
                    } else {
                        bgColor = '#334155'; // Gray (absent)
                        borderColor = '#475569';
                    }
                } else if (char) {
                    borderColor = '#94A3B8';
                }

                ctx.fillStyle = bgColor;
                ctx.beginPath();
                ctx.roundRect(bx, by, b.boxSize, b.boxSize, 6);
                ctx.fill();

                ctx.strokeStyle = borderColor;
                ctx.lineWidth = 1.5;
                ctx.stroke();

                if (char) {
                    ctx.font = 'bold 18px Inter, sans-serif';
                    ctx.fillStyle = textColor;
                    ctx.textAlign = 'center';
                    ctx.fillText(char, bx + b.boxSize / 2, by + b.boxSize / 2 + 6);
                }
            }
        }

        // On-Screen Keyboard
        const keyboard = this.getKeyboardLayout();
        for (const row of keyboard) {
            for (const key of row) {
                let kBg = '#1E293B';
                let kBorder = '#334155';
                let kText = '#F8FAFC';

                const state = this.keyStates[key.label];
                if (state === 'correct') {
                    kBg = '#10B981';
                    kBorder = '#34D399';
                } else if (state === 'present') {
                    kBg = '#D97706';
                    kBorder = '#FBBF24';
                } else if (state === 'absent') {
                    kBg = '#0B0F17';
                    kBorder = '#1E293B';
                    kText = '#64748B';
                }

                ctx.fillStyle = kBg;
                ctx.beginPath();
                ctx.roundRect(key.x, key.y, key.w, key.h, 5);
                ctx.fill();

                ctx.strokeStyle = kBorder;
                ctx.lineWidth = 1;
                ctx.stroke();

                ctx.font = key.label.length > 1 ? 'bold 10px Inter, sans-serif' : 'bold 12px Inter, sans-serif';
                ctx.fillStyle = kText;
                ctx.textAlign = 'center';
                ctx.fillText(key.label, key.x + key.w / 2, key.y + key.h / 2 + 4);
            }
        }
    }
}

window.WordleGame = WordleGame;
