{
  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";
    disko.url = "github:nix-community/disko";
    disko.inputs.nixpkgs.follows = "nixpkgs";
  };

  outputs = { self, nixpkgs, disko, ... }:

  let
    system = "x86_64-linux";
    pkgs = import nixpkgs {
      inherit system;
    };
  in {
    # Dev shell for local testing
    devShells.${system}.default = pkgs.mkShell {
      packages = [
        pkgs.uv
        pkgs.jdk21_headless
      ];

      shellHook = ''
        export JAVA_BIN="${pkgs.jdk21_headless}/bin/java"
        ${pkgs.uv}/bin/uv sync
        . .venv/bin/activate
      '';
    };
  };
}