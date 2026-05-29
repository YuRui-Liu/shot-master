from sound_track_agent.session import EmotionTag
from sound_track_agent.prompt_composer import compose_music_prompt


def test_compose_includes_core_fields():
    emo = EmotionTag(labels=["tense", "suspense"], valence=-0.5,
                     arousal=0.8, intensity=0.9)
    out = compose_music_prompt(
        global_style="末日废土，冷色调低饱和", emotion=emo, duration=8.5)
    assert "[BGM-only]" in out
    assert "末日废土，冷色调低饱和" in out
    assert "tense" in out and "suspense" in out
    assert "8.5s" in out
    assert "no vocal" in out
    assert "dialogue-friendly" in out


def test_compose_high_arousal_implies_faster_tempo_hint():
    fast = compose_music_prompt(
        "x", EmotionTag(labels=["epic"], arousal=0.9), 10.0)
    slow = compose_music_prompt(
        "x", EmotionTag(labels=["calm"], arousal=0.1), 10.0)
    assert "BPM" in fast and "BPM" in slow
    assert "110-140 BPM" in fast
    assert "60-80 BPM" in slow


def test_compose_no_emotion_falls_back_to_neutral():
    out = compose_music_prompt("古风", emotion=None, duration=5.0)
    assert "古风" in out
    assert "5.0s" in out
    assert "no vocal" in out


from sound_track_agent.prompt_composer import compose_acestep_inputs


def test_acestep_inputs_returns_triple():
    emo = EmotionTag(labels=["tense", "eerie"], arousal=0.8)
    tags, bpm, dur = compose_acestep_inputs("末日废土冷色调", emo, 12.5)
    assert isinstance(tags, str) and isinstance(bpm, int) and isinstance(dur, float)
    assert "Instrumental" in tags and "no vocals" in tags
    assert "末日废土冷色调" in tags
    assert "tense" in tags and "eerie" in tags
    assert dur == 12.5
    assert 110 <= bpm <= 140


def test_acestep_inputs_low_arousal_slow_bpm():
    _, bpm, _ = compose_acestep_inputs("古风", EmotionTag(labels=["calm"], arousal=0.1), 8.0)
    assert 60 <= bpm <= 80


def test_acestep_inputs_no_emotion_neutral():
    tags, bpm, dur = compose_acestep_inputs("treasure", None, 5.0)
    assert "treasure" in tags
    assert isinstance(bpm, int)
    assert dur == 5.0


def test_acestep_inputs_default_no_fade_out():
    """默认 fade_out=False：不能含 [Quick smooth fade out]，BGM 末段保留完整有声。"""
    tags, _, _ = compose_acestep_inputs("末日", None, 20.0)
    assert "fade out" not in tags.lower()
    assert "[Intro soft opening]" in tags
    assert "[Short main theme]" in tags


def test_acestep_inputs_fade_out_opt_in():
    """fade_out=True 还原老行为：追加 [Quick smooth fade out]。"""
    tags, _, _ = compose_acestep_inputs("末日", None, 20.0, fade_out=True)
    assert "[Quick smooth fade out]" in tags
