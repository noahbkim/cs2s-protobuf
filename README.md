# Protobuf for CS2

This repository contains a modified Protobuf snapshot that targets Counter-Strike 2.
It's forked from `v3.21.8` and has the following modifications:

- A bugfix patch for macOS (taken from the Conan recipe).
- On GCC, we specify define `_GLIBCXX_USE_CXX11_ABI=0` for ABI compatibility with the Counter-Strike server runtime.

This repository contains a Conan recipe directly adapted from [`conan-io/conan-center-index`](https://github.com/conan-io/conan-center-index/tree/master/recipes/protobuf).
You can install it locally by running `conan export .`.

The original [README and commit can be found here](https://github.com/protocolbuffers/protobuf/tree/v3.21.8).
