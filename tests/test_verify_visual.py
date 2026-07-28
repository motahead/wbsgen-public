from pathlib import Path


def test_verify_visual_owns_the_visual_output_directory():
    from tools import verify_visual

    assert verify_visual.DEFAULT_WORK_DIR == Path("output/visual")
