{
  description = "ninfs";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = inputs@{ self, nixpkgs, flake-utils }: 

    flake-utils.lib.eachDefaultSystem (system:
      let pkgs = nixpkgs.legacyPackages.${system}; in {

        packages = rec {
          haccrypto = pkgs.python3Packages.callPackage ./haccrypto.nix {};
          ninfs = pkgs.python3Packages.callPackage ./ninfs.nix { haccrypto = haccrypto; };
          default = ninfs;
        };
      }
    );
}
