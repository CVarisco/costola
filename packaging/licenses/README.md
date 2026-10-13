# Bundled runtime notices

Costola's own code is licensed under MIT (the root LICENSE).
The self-contained package includes CPython 3.14.6 and the PyInstaller 6.22.3
bootloader. Their upstream license texts are included here and in the app's
Resources/Licenses directory. PyInstaller's distribution exception is included
in its COPYING text. Build-time Python dependencies are pinned separately in
requirements-build.txt; they are not automatically part of the shipped runtime.

Inspect the PyInstaller dependency report when changing imports or the runtime:
new bundled libraries may require additional notices. Runtime license copies
must be refreshed with runtime version changes.

The python-build-standalone directory includes the upstream dependency notices
from astral-sh/python-build-standalone tag 20260718, used for the local bundled
runtime. It is a superset covering optional components and build variants;
inclusion of a notice does not mean every component is shipped. A release built
with a different CPython distribution must verify that its dependency notices
are covered before distributing the package.
