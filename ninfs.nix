{ lib, callPackage, buildPythonApplication, fetchPypi, pyctr, pycryptodomex, pypng, tkinter, setuptools, fusepy, haccrypto, stdenv }:

buildPythonApplication rec {
  pname = "ninfs";
  version = "2.0a11";

  srcs = builtins.path { path = ./.; name = "ninfs"; };

  doCheck = false;

  propagatedBuildInputs = [
    pyctr
    pycryptodomex
    pypng
    tkinter
    setuptools  # missing from requirements.txt
    fusepy
    haccrypto
  ];

  # ninfs includes its own copy of fusepy mainly for Windows support and fuse-t on macOS.
  # This isn't needed when running on Linux, and on macOS, macFUSE is required anyway.
  patchPhase = lib.optionalString (!stdenv.isDarwin) ''
    rm ninfs/fuse.py
  '';

  meta = with lib; {
    description = "FUSE filesystem Python scripts for Nintendo console files";
    homepage = "https://github.com/ihaveamac/ninfs";
    license = licenses.mit;
    platforms = platforms.unix;
    broken = !stdenv.isDarwin;
    mainProgram = "ninfs";
  };
}
