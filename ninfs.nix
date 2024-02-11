{ lib, callPackage, buildPythonApplication, fetchPypi, pyctr, pycryptodomex, pypng, tkinter, setuptools, fusepy, haccrypto, pip }:

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
}
