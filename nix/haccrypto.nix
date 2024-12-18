{ lib, buildPythonPackage, pythonOlder, fetchPypi }:

buildPythonPackage rec {
  pname = "haccrypto";
  version = "0.1.3";
  format = "setuptools";

  disabled = pythonOlder "3.6";

  src = fetchPypi {
    inherit pname version;
    hash = "sha256-PHkAxy0lq7SsdQlKSq2929Td8UDFVMleCYnq2t1xg44=";
  };

  pythonImportsCheck = [
    "haccrypto"
  ];
}
