{
  lib,
  stdenv,
  buildPythonPackage,
  fetchPypi,
  setuptools,
  pkgs,
}:

buildPythonPackage rec {
  pname = "mfusepy";
  version = "1.1.1";
  format = "pyproject";

  src = fetchPypi {
    inherit pname version;
    hash = "sha256-Nkdyem53ddR/3v9hNVk18e1e2zHFEk0jMTjyqR6gH58=";
  };

  propagatedBuildInputs = [ setuptools pkgs.fuse ];

  # No tests included
  doCheck = false;

  # On macOS, users are expected to install macFUSE. This means fusepy should
  # be able to find libfuse in /usr/local/lib.
  patchPhase = lib.optionalString (!stdenv.hostPlatform.isDarwin) ''
    substituteInPlace mfusepy.py \
      --replace "find_library('fuse')" "'${pkgs.fuse.out}/lib/libfuse.so'" \
  '';

  meta = with lib; {
    description = "Ctypes bindings for the high-level API in libfuse 2 and 3";
    longDescription = ''
      mfusepy is a Python module that provides a simple interface to FUSE and macFUSE.
      It's just one file and is implemented using ctypes to use libfuse.
    '';
    homepage = "https://github.com/mxmlnkn/mfusepy";
    license = licenses.isc;
    platforms = platforms.unix;
  };
}
