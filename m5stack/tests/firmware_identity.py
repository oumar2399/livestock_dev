"""Read-only board fingerprints. No main import, configuration or UART access."""

try:
    import uhashlib as hashlib
    import ubinascii as binascii
except ImportError:
    import hashlib
    import binascii


def main(directory=""):
    for name in ("main.py", "b4_runtime.py", "b4_protocol.py", "untimed_store.py"):
        path = directory + "/" + name if directory else name
        digest = hashlib.sha256()
        size = 0
        with open(path, "rb") as stream:
            while True:
                block = stream.read(256)
                if not block:
                    break
                digest.update(block)
                size += len(block)
        print(name, size, binascii.hexlify(digest.digest()).decode("ascii"))


if __name__ == "__main__":
    main()
