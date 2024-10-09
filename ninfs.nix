{ lib, callPackage, buildPythonApplication, fetchPypi, pyctr, pycryptodomex, pypng, tkinter, setuptools, fusepy, haccrypto, stdenv }:

buildPythonApplication rec {
  pname = "ninfs";
  version = "2.0";

  srcs = builtins.path { path = ./.; name = "ninfs"; };

  doCheck = false;

  propagatedBuildInputs = [
    pyctr
    pycryptodomex
    pypng
    tkinter
    setuptools  # missing from requirements.txt
    #fusepy  # this gets added to PYTHONPATH manually in makeWrapperArgs
    haccrypto
  ];

  makeWrapperArgs = lib.optional (!stdenv.isDarwin) [ "--prefix PYTHONPATH : ${fusepy}/${fusepy.pythonModule.sitePackages}" ];

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
    mainProgram = "ninfs";
  };
}
