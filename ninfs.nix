{ lib, pkgs, callPackage, buildPythonApplication, fetchPypi, pyctr, pycryptodomex, pypng, tkinter, setuptools, mfusepy, haccrypto, stdenv }:

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
    setuptools
    #fusepy  # this gets added to PYTHONPATH manually in makeWrapperArgs
    haccrypto
  ];

  makeWrapperArgs = lib.optional (!stdenv.isDarwin) [ "--prefix PYTHONPATH : ${mfusepy}/${mfusepy.pythonModule.sitePackages}" ];

  postInstall = lib.optionalString (!stdenv.isDarwin) ''
    mkdir -p $out/share/{applications,icons}
    NINFS_USE_NINFS_EXECUTABLE_IN_DESKTOP=1 $out/bin/ninfs --install-desktop-entry $out/share
  '';

  meta = with lib; {
    description = "FUSE filesystem Python scripts for Nintendo console files";
    homepage = "https://github.com/ihaveamac/ninfs";
    license = licenses.mit;
    platforms = platforms.unix;
    mainProgram = "ninfs";
  };
}
