{ pkgs ? import <nixpkgs> {} }:

rec {
  haccrypto = pkgs.python3Packages.callPackage ./haccrypto.nix {};
  mfusepy = pkgs.python3Packages.callPackage ./mfusepy.nix {};
  ninfs = pkgs.python3Packages.callPackage ./ninfs.nix { haccrypto = haccrypto; mfusepy = mfusepy; };
  ninfsNoGUI = pkgs.python3Packages.callPackage ./ninfs.nix { haccrypto = haccrypto; mfusepy = mfusepy; withGUI = false; };
}
