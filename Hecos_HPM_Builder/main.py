"""
Hecos HPM Builder
Version: 1.4.0
Author: Antonio Meloni

Official CLI tool to generate keys, cryptographically sign, build, and securely unpack .hpkg packages for the Hecos ecosystem.
"""
import os
import sys
import traceback
from colorama import init, Fore, Style

# Forza UTF-8 per il terminale Windows
if sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

init(autoreset=True)

# Inizializza moduli
from modules.logging_sys import log_info, log_error
from modules.crypto import generate_key_pair
from modules.scaffold import scaffold_package
from modules.builder import build_package, inspect_package, unpack_package
from modules.settings import load_config, CONFIG_TOML
from modules.edit_manifest import edit_manifest

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def print_header(title):
    clear_screen()
    print(f"{Fore.CYAN}{'=' * 60}{Style.RESET_ALL}")
    print(f" {Fore.WHITE}{Style.BRIGHT}Hecos HPM Builder{Style.RESET_ALL} {Fore.LIGHTBLACK_EX}v1.4.0 — by Antonio Meloni{Style.RESET_ALL}")
    print(f" {Fore.LIGHTBLACK_EX}Official tool for .hpkg package management{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'-' * 60}{Style.RESET_ALL}")
    print(f"   {Fore.WHITE}{Style.BRIGHT}{title}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'=' * 60}{Style.RESET_ALL}\n")

def main_menu():
    # Carica la configurazione all'avvio
    load_config()
    log_info("HPM Builder startup completed.")

    while True:
        print_header("Main Menu")
        print(f"{Fore.GREEN}1. [KEY]{Style.RESET_ALL}  {Fore.WHITE}Generate Keys{Style.RESET_ALL} {Fore.LIGHTBLACK_EX}(Crea coppia chiavi Ed25519){Style.RESET_ALL}")
        print(f"{Fore.GREEN}2. [NEW]{Style.RESET_ALL}  {Fore.WHITE}Scaffold New Package{Style.RESET_ALL} {Fore.LIGHTBLACK_EX}(Crea scheletro nuovo pacchetto){Style.RESET_ALL}")
        print(f"{Fore.GREEN}3. [BLD]{Style.RESET_ALL}  {Fore.WHITE}Validate & Build Package{Style.RESET_ALL} {Fore.LIGHTBLACK_EX}(Firma e impacchetta in .hpkg){Style.RESET_ALL}")
        print(f"{Fore.GREEN}4. [ALL]{Style.RESET_ALL}  {Fore.WHITE}Build All Packages{Style.RESET_ALL} {Fore.LIGHTBLACK_EX}(Compila tutti i sorgenti *_src){Style.RESET_ALL}")
        print(f"{Fore.GREEN}5. [CHK]{Style.RESET_ALL}  {Fore.WHITE}Inspect & Validate Package{Style.RESET_ALL} {Fore.LIGHTBLACK_EX}(Verifica manifest, firma e file){Style.RESET_ALL}")
        print(f"{Fore.GREEN}6. [EXT]{Style.RESET_ALL}  {Fore.WHITE}Extract / Unpack Package{Style.RESET_ALL} {Fore.LIGHTBLACK_EX}(Decomprime pacchetto .hpkg){Style.RESET_ALL}")
        print(f"{Fore.GREEN}7. [UNP]{Style.RESET_ALL}  {Fore.WHITE}Unpack All Packages{Style.RESET_ALL} {Fore.LIGHTBLACK_EX}(Decomprime tutti i .hpkg in cartelle *_src){Style.RESET_ALL}")
        print(f"{Fore.GREEN}8. [EDT]{Style.RESET_ALL}  {Fore.WHITE}Edit Manifest{Style.RESET_ALL} {Fore.LIGHTBLACK_EX}(Modifica versione, autore, nome...){Style.RESET_ALL}")
        print(f"{Fore.GREEN}9. [CAT]{Style.RESET_ALL}  {Fore.WHITE}Build Store Catalog{Style.RESET_ALL} {Fore.LIGHTBLACK_EX}(Genera index.json per lo Store online){Style.RESET_ALL}")
        print(f"{Fore.CYAN}D. [SYNC]{Style.RESET_ALL} {Fore.WHITE}Dev Sync{Style.RESET_ALL} {Fore.LIGHTBLACK_EX}(Sincronizza modifiche da *_src al sistema live){Style.RESET_ALL}")
        print(f"{Fore.CYAN}C. [CAP]{Style.RESET_ALL}  {Fore.WHITE}Auto-Generate Capabilities{Style.RESET_ALL} {Fore.LIGHTBLACK_EX}(Tutti i pacchetti){Style.RESET_ALL}")
        print(f"{Fore.CYAN}S. [CAP1]{Style.RESET_ALL} {Fore.WHITE}Single Package Capabilities{Style.RESET_ALL} {Fore.LIGHTBLACK_EX}(Rigenera cap. di un solo pacchetto){Style.RESET_ALL}")
        print(f"{Fore.MAGENTA}I. [INFO]{Style.RESET_ALL} {Fore.WHITE}Package Info Sheet{Style.RESET_ALL} {Fore.LIGHTBLACK_EX}(Scheda completa di UN pacchetto){Style.RESET_ALL}")
        print(f"{Fore.MAGENTA}A. [ALLI]{Style.RESET_ALL} {Fore.WHITE}All Package Info Sheets{Style.RESET_ALL} {Fore.LIGHTBLACK_EX}(Stampa tutte le schede pacchetti assieme){Style.RESET_ALL}")
        print(f"{Fore.RED}0. [EXIT]{Style.RESET_ALL} {Fore.WHITE}Close{Style.RESET_ALL}\n")
        
        print(f"{Fore.LIGHTBLACK_EX}Config File: {CONFIG_TOML}{Style.RESET_ALL}")
        choice = input(f"\n{Fore.YELLOW}Select an option:{Style.RESET_ALL} ").strip()
        
        print()
        if choice == '1':
            print_header("Key Generation")
            generate_key_pair()
            input(f"\n{Fore.LIGHTBLACK_EX}Press Enter to return to the menu...{Style.RESET_ALL}")
        elif choice == '2':
            print_header("Scaffold New Package")
            scaffold_package()
            input(f"\n{Fore.LIGHTBLACK_EX}Press Enter to return to the menu...{Style.RESET_ALL}")
        elif choice == '3':
            print_header("Validate & Build Package")
            build_package()
            input(f"\n{Fore.LIGHTBLACK_EX}Press Enter to return to the menu...{Style.RESET_ALL}")
        elif choice == '4':
            print_header("Build All Packages")
            from modules.builder import build_all_packages
            build_all_packages()
            input(f"\n{Fore.LIGHTBLACK_EX}Press Enter to return to the menu...{Style.RESET_ALL}")
        elif choice == '5':
            print_header("Inspect & Validate Package")
            inspect_package()
            input(f"\n{Fore.LIGHTBLACK_EX}Press Enter to return to the menu...{Style.RESET_ALL}")
        elif choice == '6':
            print_header("Extract / Unpack Package")
            unpack_package()
            input(f"\n{Fore.LIGHTBLACK_EX}Press Enter to return to the menu...{Style.RESET_ALL}")
        elif choice == '7':
            print_header("Unpack All Packages")
            from modules.builder import unpack_all_packages
            unpack_all_packages()
            input(f"\n{Fore.LIGHTBLACK_EX}Press Enter to return to the menu...{Style.RESET_ALL}")
        elif choice == '8':
            print_header("Edit Manifest")
            edit_manifest()
            input(f"\n{Fore.LIGHTBLACK_EX}Press Enter to return to the menu...{Style.RESET_ALL}")
        elif choice == '9':
            print_header("Build Store Catalog")
            from modules.store_generator import generate_store_catalog
            generate_store_catalog()
            input(f"\n{Fore.LIGHTBLACK_EX}Press Enter to return to the menu...{Style.RESET_ALL}")
        elif choice.upper() == 'D':
            print_header("Dev Sync (Sincronizza modifiche live)")
            from modules.dev_sync import dev_sync_package
            dev_sync_package()
            input(f"\n{Fore.LIGHTBLACK_EX}Press Enter to return to the menu...{Style.RESET_ALL}")
        elif choice.upper() == 'C':
            print_header("Auto-Generate Capabilities — Tutti i pacchetti")
            from modules.capabilities_gen import generate_all_capabilities
            generate_all_capabilities()
            input(f"\n{Fore.LIGHTBLACK_EX}Press Enter to return to the menu...{Style.RESET_ALL}")
        elif choice.upper() == 'S':
            print_header("Single Package Capabilities")
            from modules.capabilities_gen import generate_single_capabilities
            generate_single_capabilities()
            input(f"\n{Fore.LIGHTBLACK_EX}Press Enter to return to the menu...{Style.RESET_ALL}")
        elif choice.upper() == 'I':
            print_header("Package Info Sheet")
            from modules.capabilities_gen import show_package_sheet
            show_package_sheet()
            input(f"\n{Fore.LIGHTBLACK_EX}Press Enter to return to the menu...{Style.RESET_ALL}")
        elif choice.upper() == 'A':
            print_header("All Package Info Sheets")
            from modules.capabilities_gen import show_all_package_sheets
            show_all_package_sheets()
            input(f"\n{Fore.LIGHTBLACK_EX}Press Enter to return to the menu...{Style.RESET_ALL}")
        elif choice == '0':
            break

if __name__ == "__main__":
    try:
        main_menu()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        log_error(f"Fatal Error: {e}")
        traceback.print_exc()
        input("\nPress Enter to exit...")
