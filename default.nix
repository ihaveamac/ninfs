{
  pkgs ? import <nixpkgs> { },
  # just so i can use the same pinned version as the flake...
  pyctr ? (
    let
      flakeLock = builtins.fromJSON (builtins.readFile ./flake.lock);
      pyctr-repo = import (builtins.fetchTarball (
        with flakeLock.nodes.pyctr.locked;
        {
          url = "https://github.com/${owner}/${repo}/archive/${rev}.tar.gz";
        }
      )) { inherit pkgs; };
    in
    pyctr-repo.pyctr
  ),
}:

rec {
  haccrypto = pkgs.python3Packages.callPackage ./nix/haccrypto.nix { };
  mfusepy = pkgs.python3Packages.callPackage ./nix/mfusepy.nix { };
  ninfs = pkgs.python3Packages.callPackage ./package.nix {
    inherit pyctr;
    haccrypto = haccrypto;
    mfusepy = mfusepy;
  };
  ninfsNoGUI = ninfs.override { withGUI = false; };
  #ninfsNoGUI = pkgs.python3Packages.callPackage ./ninfs.nix { haccrypto = haccrypto; mfusepy = mfusepy; withGUI = false; };
}
