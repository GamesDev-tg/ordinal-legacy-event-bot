class FestivalAudio {
    constructor() {
        this.ctx = null;
        this.muted = false;
    }

    init() {
        if (!this.ctx) {
            const AudioContext = window.AudioContext || window.webkitAudioContext;
            this.ctx = new AudioContext();
        }
        if (this.ctx.state === 'suspended') {
            this.ctx.resume();
        }
    }

    playTone(freq, duration, type = 'sine', gainVal = 0.2) {
        if (this.muted) return;
        this.init();
        try {
            const osc = this.ctx.createOscillator();
            const gain = this.ctx.createGain();
            osc.type = type;
            osc.frequency.setValueAtTime(freq, this.ctx.currentTime);
            gain.gain.setValueAtTime(gainVal, this.ctx.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.001, this.ctx.currentTime + duration);
            osc.connect(gain);
            gain.connect(this.ctx.destination);
            osc.start();
            osc.stop(this.ctx.currentTime + duration);
        } catch (e) {}
    }

    playDholBeat() {
        if (this.muted) return;
        this.init();
        try {
            const osc = this.ctx.createOscillator();
            const gain = this.ctx.createGain();
            osc.type = 'triangle';
            osc.frequency.setValueAtTime(150, this.ctx.currentTime);
            osc.frequency.exponentialRampToValueAtTime(40, this.ctx.currentTime + 0.18);
            gain.gain.setValueAtTime(0.45, this.ctx.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.001, this.ctx.currentTime + 0.2);
            osc.connect(gain);
            gain.connect(this.ctx.destination);
            osc.start();
            osc.stop(this.ctx.currentTime + 0.2);
        } catch (e) {}
    }

    // GDD: Aerial multi-burst explosion sound (Chakri 3 Points)
    playAerialMultiBurst() {
        if (this.muted) return;
        this.init();
        try {
            // Initial lift rocket screech
            this.playTone(320, 0.12, 'sawtooth', 0.15);
            // Cascading explosion bursts
            [0.1, 0.25, 0.42].forEach((delay, idx) => {
                setTimeout(() => {
                    if (this.muted) return;
                    // Low thump
                    const osc = this.ctx.createOscillator();
                    const gain = this.ctx.createGain();
                    osc.type = 'sine';
                    osc.frequency.setValueAtTime(90 - idx * 15, this.ctx.currentTime);
                    osc.frequency.exponentialRampToValueAtTime(25, this.ctx.currentTime + 0.3);
                    gain.gain.setValueAtTime(0.4, this.ctx.currentTime);
                    gain.gain.exponentialRampToValueAtTime(0.001, this.ctx.currentTime + 0.35);
                    osc.connect(gain);
                    gain.connect(this.ctx.destination);
                    osc.start();
                    osc.stop(this.ctx.currentTime + 0.35);

                    // Crackling noise burst
                    const bufSize = this.ctx.sampleRate * 0.28;
                    const buf = this.ctx.createBuffer(1, bufSize, this.ctx.sampleRate);
                    const data = buf.getChannelData(0);
                    for (let i = 0; i < bufSize; i++) data[i] = Math.random() * 2 - 1;
                    const noise = this.ctx.createBufferSource();
                    noise.buffer = buf;
                    const filter = this.ctx.createBiquadFilter();
                    filter.type = 'bandpass';
                    filter.frequency.value = 1200 + Math.random() * 800;
                    const ngain = this.ctx.createGain();
                    ngain.gain.setValueAtTime(0.35, this.ctx.currentTime);
                    ngain.gain.exponentialRampToValueAtTime(0.001, this.ctx.currentTime + 0.28);
                    noise.connect(filter);
                    filter.connect(ngain);
                    ngain.connect(this.ctx.destination);
                    noise.start();
                }, delay * 1000);
            });
        } catch (e) {}
    }

    // GDD: Silver shower sparkle sound (Chakri 2 Points)
    playSilverShower() {
        if (this.muted) return;
        this.init();
        try {
            const bufSize = this.ctx.sampleRate * 0.45;
            const buf = this.ctx.createBuffer(1, bufSize, this.ctx.sampleRate);
            const data = buf.getChannelData(0);
            for (let i = 0; i < bufSize; i++) data[i] = Math.random() * 2 - 1;
            const noise = this.ctx.createBufferSource();
            noise.buffer = buf;
            const filter = this.ctx.createBiquadFilter();
            filter.type = 'highpass';
            filter.frequency.value = 3500;
            const gain = this.ctx.createGain();
            gain.gain.setValueAtTime(0.25, this.ctx.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.001, this.ctx.currentTime + 0.45);
            noise.connect(filter);
            filter.connect(gain);
            gain.connect(this.ctx.destination);
            noise.start();

            // High bell shimmer
            [1200, 1600, 2100].forEach((f, i) => {
                setTimeout(() => this.playTone(f, 0.15, 'sine', 0.12), i * 80);
            });
        } catch (e) {}
    }

    // GDD: Fountain sizzle sound (Chakri 1 Point)
    playFountainSizzle() {
        if (this.muted) return;
        this.init();
        try {
            const bufSize = this.ctx.sampleRate * 0.35;
            const buf = this.ctx.createBuffer(1, bufSize, this.ctx.sampleRate);
            const data = buf.getChannelData(0);
            for (let i = 0; i < bufSize; i++) data[i] = Math.random() * 2 - 1;
            const noise = this.ctx.createBufferSource();
            noise.buffer = buf;
            const filter = this.ctx.createBiquadFilter();
            filter.type = 'bandpass';
            filter.frequency.value = 2200;
            const gain = this.ctx.createGain();
            gain.gain.setValueAtTime(0.18, this.ctx.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.001, this.ctx.currentTime + 0.35);
            noise.connect(filter);
            filter.connect(gain);
            gain.connect(this.ctx.destination);
            noise.start();
        } catch (e) {}
    }

    // GDD: Petal Notes (Note C4: 261.63Hz, E4: 329.63Hz, G4: 392.00Hz, B4: 493.88Hz)
    playRangoliNote(index) {
        const freqs = [261.63, 329.63, 392.00, 493.88];
        const freq = freqs[index % freqs.length];
        this.playTone(freq, 0.38, 'sine', 0.28);
        // Subtle bell harmonic
        this.playTone(freq * 2, 0.22, 'triangle', 0.12);
    }

    playSweetCatch() {
        this.playTone(659.25, 0.08, 'sine', 0.18);
        setTimeout(() => this.playTone(880.00, 0.12, 'sine', 0.22), 60);
    }

    playHazardHit() {
        if (this.muted) return;
        this.init();
        try {
            // Sizzle hiss
            const bufSize = this.ctx.sampleRate * 0.2;
            const buf = this.ctx.createBuffer(1, bufSize, this.ctx.sampleRate);
            const data = buf.getChannelData(0);
            for (let i = 0; i < bufSize; i++) data[i] = Math.random() * 2 - 1;
            const noise = this.ctx.createBufferSource();
            noise.buffer = buf;
            const filter = this.ctx.createBiquadFilter();
            filter.type = 'lowpass';
            filter.frequency.value = 900;
            const gain = this.ctx.createGain();
            gain.gain.setValueAtTime(0.25, this.ctx.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.001, this.ctx.currentTime + 0.2);
            noise.connect(filter);
            filter.connect(gain);
            gain.connect(this.ctx.destination);
            noise.start();
        } catch (e) {}
    }

    playSuccessChime() {
        this.playTone(523.25, 0.15, 'sine', 0.22);
        setTimeout(() => this.playTone(659.25, 0.2, 'sine', 0.25), 110);
        setTimeout(() => this.playTone(783.99, 0.25, 'sine', 0.28), 220);
        setTimeout(() => this.playTone(1046.50, 0.45, 'sine', 0.32), 330);
    }

    playShubhBlessing() {
        // Grand temple chimes
        [523.25, 659.25, 783.99, 987.77, 1046.50].forEach((f, idx) => {
            setTimeout(() => {
                this.playTone(f, 0.6, 'sine', 0.25);
                this.playTone(f * 1.5, 0.3, 'triangle', 0.1);
            }, idx * 90);
        });
    }

    playTap() {
        this.playTone(480, 0.05, 'triangle', 0.12);
    }

    // Backward compatibility aliases
    playFireworkBurst() {
        this.playAerialMultiBurst();
    }
}
window.festivalAudio = new FestivalAudio();
