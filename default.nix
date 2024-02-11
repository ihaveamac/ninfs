{ pkgs ? import <nixpkgs> {} }:

rec {
  haccrypto = pkgs.python3Packages.callPackage ./haccrypto.nix {};
  ninfs = pkgs.python3Packages.callPackage ./ninfs.nix { haccrypto = haccrypto; };
}
