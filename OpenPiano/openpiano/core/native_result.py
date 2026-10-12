

def check_native_result(result, action: str) -> None:
    if isinstance(result, int) and result < 0:
        raise RuntimeError(f'FluidSynth could not {action}.')


def release_native_note(synth, channel: int, note: int) -> None:
    result = synth.noteoff(channel, note)
    if result != -1:
        check_native_result(result, 'release a note')
