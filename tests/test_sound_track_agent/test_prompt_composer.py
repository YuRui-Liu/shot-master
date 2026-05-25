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
