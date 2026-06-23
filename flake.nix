{
  description = "Homelab development environment";

  # TODO: Remove flux-local after konflate is deployed and tested

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

        python = pkgs.python313;

        flux-local = python.pkgs.callPackage ./flux-local.nix {
          inherit (pkgs)
            kustomize
            kubernetes-helm
            fluxcd
            git
            ;
          inherit (python.pkgs) pytestCheckHook syrupy anyio;
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
          flux-local
          pkgs.flate
          sops
          restic
        ];
      in
      {
        packages.flux-local = flux-local;
        packages.default = flux-local;

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
