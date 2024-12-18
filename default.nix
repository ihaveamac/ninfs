{ pkgs ? import <nixpkgs> {} }:

rec {
  haccrypto = pkgs.python3Packages.callPackage ./nix/haccrypto.nix {};
  mfusepy = pkgs.python3Packages.callPackage ./nix/mfusepy.nix {};
  ninfs = pkgs.python3Packages.callPackage ./package.nix { haccrypto = haccrypto; mfusepy = mfusepy; };
  ninfsNoGUI = ninfs.override { withGUI = false; };
  #ninfsNoGUI = pkgs.python3Packages.callPackage ./ninfs.nix { haccrypto = haccrypto; mfusepy = mfusepy; withGUI = false; };
}
