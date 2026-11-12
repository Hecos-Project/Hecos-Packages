# Voice Forge

**Voice Forge** is an acoustic vocal timbre sculpting and reference forging studio engineered specifically for Fish Speech S2-Pro in Hecos.

## Key Features
- **100% Original Vocal Timbres**: Forge unique voices from Fish Speech random seeds or Kokoro TTS without relying on real human voices, protecting privacy and copyright.
- **Physical Vocal Tract Sculpting**: Manipulate fundamental frequency (F0), intonation dynamics, and vocal tract length / cavity scaling via high-precision WORLD vocoder (`pyworld`) decomposition.
- **Micro-Texture Controls**: Modulate vocal breathiness / whispering, micro-jitter and subharmonic fry (gravel/rasp), and physiological low-frequency tremor (5.5 Hz).
- **4-Band Console Equalizer**: Precision second-order biquad acoustic filters shaping chest Body (150 Hz), throat Warmth (400 Hz), phonetic Presence (3 kHz), and Air sheen (10 kHz).
- **Multilingual Reference Corpus**: Native phonetically balanced pangrams and calibration sentences for Italian, English, German, French, Spanish, Japanese, and Chinese. Ensures reference audio and text match targets precisely, preventing foreign accent contamination.
- **40 Bundled Presets**: 24 Base presets (Man, Woman, Boy, Girl, Child, Elderly) and 16 Cinematic character presets (Witch, Demon, Giant, Android, Ghost, Whisper, Ogre, Goblin, Elf, Fairy, Vampire, Narrator, Alien, Angel, Dwarf, Siren).
- **Direct Fish Speech Registry**: One-click bake writes reference audio directly to `assets/voice_clones` and registers new presets into `audio.yaml` for instant use in Hecos chat, TTS dropdowns, and global presets.
