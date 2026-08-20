{
  description = "tact-downloader dev shell with Playwright dependencies";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs =
    { self, nixpkgs }:
    let
      system = "x86_64-linux";
      pkgs = import nixpkgs { inherit system; };
      playwrightDeps = with pkgs; [
        alsa-lib
        at-spi2-atk
        at-spi2-core
        atk
        cairo
        cups
        dbus
        expat
        glib
        gtk3
        libdrm
        libgcc.lib
        mesa
        nspr
        nss
        pango
        stdenv.cc.cc.lib
        zlib
        libX11
        libXcomposite
        libXdamage
        libXext
        libXfixes
        libXrandr
        libxcb
        libxkbcommon
        libxshmfence
        libXScrnSaver
        libXtst
      ];
    in
    {
      devShells.${system}.default = pkgs.mkShell {
        packages = with pkgs; [
          uv
          nodejs
          playwright-driver.browsers
        ];
        LD_LIBRARY_PATH = pkgs.lib.makeLibraryPath playwrightDeps;
        PLAYWRIGHT_BROWSERS_PATH = "${pkgs.playwright-driver.browsers}";
        PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD = "1";
        shellHook = ''
          echo "tact-downloader dev shell: Playwright browsers from nixpkgs"
          echo "Requires programs.nix-ld.enable = true (no libraries needed) for uv's node to run"
        '';
      };
    };
}
