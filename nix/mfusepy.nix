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
  version = "1.0.0";
  format = "pyproject";

  src = fetchPypi {
    inherit pname version;
    hash = "sha256-vpIjTLMw4l3wBPsR8uK9wghNTRD7awDy9TRUC8ZsGKI=";
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
