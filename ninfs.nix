{ lib, callPackage, buildPythonApplication, fetchPypi, pyctr, pycryptodomex, pypng, tkinter, setuptools, fusepy, haccrypto, pip, stdenv, pkgs }:

buildPythonApplication rec {
  pname = "ninfs";
  version = "2.0a11";
  format = "setuptools";

  srcs = builtins.path { path = ./.; name = "ninfs"; };

  propagatedBuildInputs = [
    pyctr
    pycryptodomex
    pypng
    tkinter
    setuptools  # missing from requirements.txt
    fusepy  # despite ninfs including its own copy of fuse.py, it can't find it for some reason
    pip
    haccrypto
  ];

  makeWrapperArgs = lib.optional (!stdenv.isDarwin) [
    "--set FUSE_LIBRARY_PATH ${pkgs.fuse}/lib/libfuse.so.2"
  ];

  meta = with lib; {
    description = "FUSE filesystem Python scripts for Nintendo console files";
    homepage = "https://github.com/ihaveamac/ninfs";
    license = licenses.mit;
    # until i figure out what's up with libfuse on linux
    platforms = platforms.unix;
    broken = !stdenv.isDarwin;
    mainProgram = "ninfs";
  };
}
