# Dotfiles

These are my dotfiles.

I install them using [GNU Stow][GNU Stow] but you can use them however you want
to.

## Setup

1. Install GNU Stow. Most distributions package it under the name `stow`.
1. Clone this repository into your home directory. `git clone
   https://github.com/hashhar/dotfiles.git ~/dotfiles`.
1. Individually install the dotfile sets that you want using `stow -R
   dotfile-set`. `dotfile-set` is simply the name of any directory in the
   repository.

I'll be providing a bootstrapping strip in due course of time. In the meantime
I recommend you read [this][Xero's GNU Stow Guide] to get a good idea of how
GNU Stow works and how to use it to manage your dotfiles.

## Questions? Suggestions? Ideas?

Open an issue or tweet me at [@hashhar][Twitter].

[GNU Stow]: https://www.gnu.org/software/stow
[Xero's GNU Stow Guide]: http://blog.xero.nu/managing_dotfiles_with_gnu_stow
[Twitter]: https://twitter.com/hashhar
