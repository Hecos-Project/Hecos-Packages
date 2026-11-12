"""
Voice Forge - Recipe Schema
Defines the parameters that shape an original vocal timbre.
"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

class VoiceRecipe(BaseModel):
    id: str = Field(..., description="Unique slug for the timbre")
    name: str = Field(..., description="Human readable name")
    description: str = Field("", description="Description of the timbre and character")
    category: str = Field("custom", description="base | cinematic | custom")
    
    # Language and reference text
    language: str = Field("en", description="Language code: it, en, de, fr, es, ja, zh")
    reference_text: str = Field("", description="Phonetically balanced text pronounced by reference")
    
    # Source
    source_type: str = Field("synthetic_fish", description="synthetic_fish | synthetic_kokoro | file")
    source_file: Optional[str] = Field(None, description="Path or basename of source audio if file")
    source_seed: Optional[int] = Field(42, description="Random seed if synthetic_fish")
    source_speaker: Optional[str] = Field("af_heart", description="Speaker name if synthetic_kokoro")
    
    # Timbre sculpting parameters (WORLD Vocoder)
    pitch_semitones: float = Field(0.0, ge=-12.0, le=12.0, description="Pitch shift in semitones")
    pitch_dynamics: float = Field(1.0, ge=0.0, le=2.0, description="1.0 = normal, 0.0 = robotic monotone, 1.5+ = expressive")
    vocal_tract_ratio: float = Field(1.0, ge=0.65, le=1.45, description="Formant shift: <1.0 = larger cavity (giant), >1.0 = smaller (child)")
    
    # Texture & Physicality
    breathiness: float = Field(0.0, ge=0.0, le=1.0, description="Aperiodicity boost for breathy/whispered voice")
    roughness: float = Field(0.0, ge=0.0, le=1.0, description="Micro-jitter and subharmonics for gravel/rasp")
    tremolo: float = Field(0.0, ge=0.0, le=1.0, description="Slow tremor (5-6 Hz) for elderly/frail voice")
    
    # Acoustic Equalization (4 bands)
    body_gain_db: float = Field(0.0, ge=-12.0, le=12.0, description="Low-shelf at 150 Hz (fullness/chest resonance)")
    warmth_gain_db: float = Field(0.0, ge=-12.0, le=12.0, description="Peaking at 400 Hz (warmth/thickness)")
    presence_gain_db: float = Field(0.0, ge=-12.0, le=12.0, description="Peaking at 3000 Hz (clarity/intelligibility)")
    air_gain_db: float = Field(0.0, ge=-12.0, le=12.0, description="High-shelf at 10000 Hz (air/sparkle)")
    
    # Speech pace
    tempo_ratio: float = Field(1.0, ge=0.8, le=1.25, description="Speaking pace adjustment")
    
    # Blending / Morphing
    blend_source_file: Optional[str] = Field(None, description="Second audio source to blend with")
    blend_ratio: float = Field(0.0, ge=0.0, le=1.0, description="0.0 = 100% source A, 1.0 = 100% source B")
    
    # Tags & Metadata
    tags: List[str] = Field(default_factory=list)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
