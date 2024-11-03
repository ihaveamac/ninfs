{
  description = "ninfs";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
    pyctr.url = "github:ihaveamac/pyctr/master";
    pyctr.inputs.nixpkgs.follows = "nixpkgs";
    pyctr.inputs.flake-utils.follows = "flake-utils";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = inputs@{ self, nixpkgs, flake-utils, pyctr }:

    flake-utils.lib.eachDefaultSystem (system:
      let pkgs = nixpkgs.legacyPackages.${system}; in {

        packages = rec {
          haccrypto = pkgs.python3Packages.callPackage ./haccrypto.nix {};
          mfusepy = pkgs.python3Packages.callPackage ./mfusepy.nix {};
          ninfs = pkgs.python3Packages.callPackage ./ninfs.nix { haccrypto = haccrypto; mfusepy = mfusepy; pyctr = pyctr.packages.${system}.pyctr; };
          default = ninfs;
        };
      }
    );
}
