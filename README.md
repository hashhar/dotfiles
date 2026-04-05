# Dotfiles

My dotfiles, managed with [chezmoi](https://chezmoi.io).

## Setup

1. [Install chezmoi](https://chezmoi.io/install/).
2. Run:
   ```sh
   chezmoi init --apply https://github.com/hashhar/dotfiles.git
   ```
3. Find any private config files that need to be filled in:
   ```sh
   find $(chezmoi source-path) -name "*.example.md"
   ```
   For each result, copy it to the same path without `.example` and fill in your values, then re-run `chezmoi apply`.

## Structure

| Path | Description |
|------|-------------|
| `dot_claude/` | Claude Code settings, statusline script, and skills |
| `dot_config/git/` | Git config with per-context identity routing via `includeIf` |

## License

MIT
