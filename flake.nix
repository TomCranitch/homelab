{
  description = "Homelab development environment";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs =
    {
      self,
      nixpkgs,
      flake-utils,
    }:
    flake-utils.lib.eachDefaultSystem (
      system:
      let
        pkgs = import nixpkgs {
          inherit system;
          config.allowUnfree = true;
        };

        devShellTools = with pkgs; [
          kubectl
          fluxcd
          kustomize
          kubernetes-helm
          sops
          age
          k9s
          talosctl
          talhelper
          yq-go
          sops
          restic
        ];
      in
      {
        devShells.default = pkgs.mkShell {
          buildInputs = devShellTools;

          shellHook = ''
            echo "🛡️ Homelab development environment loaded"
            echo "Tools available: $(ls ${pkgs.lib.makeBinPath devShellTools} | tr '\n' ' ')"
          '';
        };
      }
    );
}
