#Configuration for a nixos VM
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

    # Server VM config
    nixosConfigurations.mc-server = nixpkgs.lib.nixosSystem {
      modules = [
        disko.nixosModules.disko
        ({ pkgs, modulesPath, ... }: {
          imports = [
            (modulesPath + "/profiles/qemu-guest.nix") # Standard VM drivers
            ./disko-config.nix
          ];

          boot.loader.systemd-boot.enable = true;
          services.openssh.enable = true;
          services.openssh.settings.PermitRootLogin = "prohibit-password";
          users.mutableUsers = false;
          users.users.root = {
            password = "password";
            openssh.authorizedKeys.keys = [
              "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIHQEYO4yt6bBerFfe0WJKGVkeDEuZG+raWL9FhAFwI90" 
            ];
          };
          users.users.mc-server = {
            isSystemUser = true;
            home = "/var/lib/mc-server";
            group = "mc-server";
          };
          users.groups.mc-server = {};

          environment.localBinInPath = true;
          programs.nix-ld.enable = true;
          environment.systemPackages = with pkgs; [
            uv
            jdk21_headless
            bash
            coreutils
          ];

          networking.firewall.allowedTCPPorts = [ 25565 ];
          networking.firewall.allowedUDPPorts = [ 24454 ];

          systemd.services.mc-server = {
            description = "Minecraft Server Pod";
            after = [ "network-online.target" "nss-lookup.target" ];
            wants = [ "network-online.target" ];
            wantedBy = [ "multi-user.target" ];

            environment = {
              JAVA_BIN = "${pkgs.jdk21_headless}/bin/java";
            };

            # TODO: Switch from docker to just running uv directly here
            serviceConfig = {
              Type = "simple";
              User = "mc-server";
              Group = "mc-server";
              
              # This automatically creates /var/lib/mc-server with correct permissions
              StateDirectory = "mc-server"; 
              WorkingDirectory = "/var/lib/mc-server";
              StateDirectoryMode = "0750";

              # We only use ExecStartPre for the Git logic now
              ExecStartPre = (pkgs.writeShellScript "git-sync" ''
                if [ ! -d ".git" ]; then
                  ${pkgs.git}/bin/git clone https://github.com/haroonsyed/mc_server_manager.git .
                else
                  ${pkgs.git}/bin/git pull origin main
                fi
                ${pkgs.uv}/bin/uv sync
              '');

              ExecStart = "${pkgs.uv}/bin/uv run start.py";
              Restart = "always";
            };
          };
        })
      ];
    };
  };
}