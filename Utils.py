VERBOSITY_LEVEL = 1  # Adjust verbosity (0=minimal, 1=normal, 2=verbose)


def log(message, level="info", verbosity=1):
    if verbosity <= VERBOSITY_LEVEL:
        colors = {
            "info": "\033[94m",
            "success": "\033[92m",
            "warning": "\033[93m",
            "error": "\033[91m"
        }
        reset_color = "\033[0m"
        print(f"{colors.get(level, colors['info'])}[{level.upper()}] {message}{reset_color}")
