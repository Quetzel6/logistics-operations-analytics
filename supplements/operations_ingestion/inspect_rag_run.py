"""Read completed observations even after SIGKILL; never contact a model."""
import argparse
import json
from pathlib import Path


def inspect(directory):
    raw = (Path(directory) / 'events.jsonl').read_bytes()
    lines = raw.splitlines(keepends=True)
    partial_tail = bool(lines and not lines[-1].endswith(b'\n'))
    if partial_tail:
        lines.pop()  # Report a torn last append explicitly; do not ignore interior corruption.
    events = [json.loads(line) for line in lines]
    if any(e['sequence'] != i for i, e in enumerate(events, 1)):
        raise ValueError('journal_sequence_gap')
    observations = [e['observation'] for e in events if e['event'] == 'observation']
    finished = [e for e in events if e['event'] == 'run_finished']
    return dict(state=finished[-1]['state'] if finished else 'incomplete',
                completed_observations=len(observations), partial_tail=partial_tail,
                observations=observations,
                note='incomplete means no durable finish event; it does not prove whether an outstanding request reached Ollama')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(inspect(args.directory), indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
