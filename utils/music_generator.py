"""
music_generator.py — Generates unique ambient background music for each Reel.
Uses numpy/scipy to create lofi-style ambient tracks procedurally.
Different mood per post type. No copyright issues.
"""

import numpy as np
import wave
import os
import random
import tempfile
from utils.logger import get_logger

logger = get_logger("music_generator")

SAMPLE_RATE = 44100


def _sine_wave(freq, duration, sr=SAMPLE_RATE, amplitude=0.3):
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    return amplitude * np.sin(2 * np.pi * freq * t)


def _apply_envelope(wave, sr=SAMPLE_RATE, fade_duration=0.5):
    """Apply fade in/out to avoid clicks."""
    fade_samples = int(sr * fade_duration)
    fade_in = np.linspace(0, 1, fade_samples)
    fade_out = np.linspace(1, 0, fade_samples)
    result = wave.copy()
    result[:fade_samples] *= fade_in
    result[-fade_samples:] *= fade_out
    return result


def _generate_lofi_ambient(duration: float, seed: int = None) -> np.ndarray:
    """Generate a lofi ambient track — calm, slow chords."""
    if seed:
        random.seed(seed)
        np.random.seed(seed)

    # Base chord frequencies (minor pentatonic scale variations)
    chord_sets = [
        [220.0, 261.6, 329.6, 392.0],   # A minor feel
        [196.0, 246.9, 293.7, 349.2],   # G minor feel
        [174.6, 220.0, 261.6, 311.1],   # F minor feel
        [233.1, 277.2, 349.2, 415.3],   # Bb minor feel
    ]
    chords = random.choice(chord_sets)

    track = np.zeros(int(SAMPLE_RATE * duration))

    # Layer slow sine waves (pad sound)
    for freq in chords:
        # Slightly detune for width
        for detune in [-0.5, 0, 0.5]:
            wave = _sine_wave(freq + detune, duration, amplitude=0.06)
            # Add slow vibrato
            t = np.linspace(0, duration, len(wave))
            vibrato = 1 + 0.002 * np.sin(2 * np.pi * 0.3 * t)
            track += wave * vibrato

    # Add sub bass (very low, subtle)
    bass_freq = chords[0] / 2
    bass = _sine_wave(bass_freq, duration, amplitude=0.08)
    track += bass

    # Add gentle noise texture (like vinyl crackle)
    noise = np.random.normal(0, 0.003, len(track))
    # Low-pass the noise
    from scipy.signal import butter, filtfilt
    b, a = butter(2, 800 / (SAMPLE_RATE / 2), btype='low')
    noise = filtfilt(b, a, noise)
    track += noise

    # Normalize
    track = _apply_envelope(track, fade_duration=1.0)
    max_val = np.max(np.abs(track))
    if max_val > 0:
        track = track / max_val * 0.4

    return track


def _generate_tech_pulse(duration: float, seed: int = None) -> np.ndarray:
    """Generate a tech/news style pulse — energetic, forward."""
    if seed:
        random.seed(seed)
        np.random.seed(seed)

    track = np.zeros(int(SAMPLE_RATE * duration))

    # High pad
    pad_freqs = random.choice([
        [440.0, 554.4, 659.3],
        [493.9, 587.3, 740.0],
        [415.3, 523.3, 622.3],
    ])
    for freq in pad_freqs:
        wave = _sine_wave(freq, duration, amplitude=0.05)
        track += wave

    # Pulsing mid tone
    pulse_freq = random.choice([220.0, 246.9, 261.6])
    t = np.linspace(0, duration, int(SAMPLE_RATE * duration))
    pulse_rate = random.choice([1.0, 1.5, 2.0])
    pulse_env = (np.sin(2 * np.pi * pulse_rate * t) + 1) / 2
    pulse = _sine_wave(pulse_freq, duration, amplitude=0.08) * pulse_env
    track += pulse

    # Sub bass
    bass = _sine_wave(pulse_freq / 2, duration, amplitude=0.07)
    track += bass

    track = _apply_envelope(track, fade_duration=0.8)
    max_val = np.max(np.abs(track))
    if max_val > 0:
        track = track / max_val * 0.4

    return track


def _generate_dramatic(duration: float, seed: int = None) -> np.ndarray:
    """Generate a dramatic/tense track — for differentiator/hot take posts."""
    if seed:
        random.seed(seed)
        np.random.seed(seed)

    track = np.zeros(int(SAMPLE_RATE * duration))

    # Low ominous drone
    drone_freqs = [random.choice([110.0, 123.5, 130.8]), ]
    for freq in drone_freqs:
        for harmonic in [1, 2, 3]:
            wave = _sine_wave(freq * harmonic, duration, amplitude=0.06 / harmonic)
            track += wave

    # Slow swelling
    t = np.linspace(0, duration, int(SAMPLE_RATE * duration))
    swell = (np.sin(2 * np.pi * 0.15 * t) + 1) / 2
    track = track * (0.4 + 0.6 * swell)

    # Tension string-like tone
    string_freq = random.choice([277.2, 311.1, 329.6])
    string = _sine_wave(string_freq, duration, amplitude=0.04)
    track += string

    track = _apply_envelope(track, fade_duration=1.2)
    max_val = np.max(np.abs(track))
    if max_val > 0:
        track = track / max_val * 0.35

    return track


def generate_background_music(
    post_type: str,
    duration: float,
    output_path: str = None,
    seed: int = None,
) -> str:
    """
    Generate unique background music for a Reel.

    Args:
        post_type: daily_brief | learning | differentiator
        duration: Length in seconds
        output_path: Where to save the WAV file
        seed: Random seed for reproducibility (use timestamp for uniqueness)

    Returns:
        Path to generated WAV file
    """
    if seed is None:
        seed = random.randint(0, 999999)

    logger.info(f"Generating background music for [{post_type}] seed={seed}")

    if post_type == "differentiator":
        audio = _generate_dramatic(duration, seed=seed)
    elif post_type == "learning":
        audio = _generate_lofi_ambient(duration, seed=seed)
    else:
        # daily_brief — randomly pick lofi or tech
        if seed % 2 == 0:
            audio = _generate_lofi_ambient(duration, seed=seed)
        else:
            audio = _generate_tech_pulse(duration, seed=seed)

    # Save as WAV
    if not output_path:
        output_path = tempfile.mktemp(suffix=".wav")

    audio_int16 = (audio * 32767).astype(np.int16)
    with wave.open(output_path, 'w') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(audio_int16.tobytes())

    logger.info(f"Background music saved: {output_path}")
    return output_path
