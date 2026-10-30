"""Import Tekken 7 presets onto native Paul; requires the matching runtime."""
import argparse
import sys


def main(argv=None):
    from ttt2char import InputError, native_costumes, pack, signals
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('presets', nargs='*')
    parser.add_argument('--game', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--tekken7')
    parser.add_argument('--remove', action='store_true')
    parser.add_argument('--cached', help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    signals.stop_on_signals()
    try:
        out = pack.output_folder(args.out)
        if args.remove:
            native_costumes.remove(out)
            print('@done', flush=True)
            return 0
        tekken7 = args.tekken7
        if not tekken7:
            from ttt2char.tekken7 import autodump
            tekken7 = autodump.find_tekken7().game
        native_costumes.build(args.game, tekken7, out, args.presets,
                              log=lambda message: print(message, flush=True), cached=args.cached)
        return 0
    except (InputError, OSError, ValueError) as error:
        print('@error ' + str(error), flush=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())
