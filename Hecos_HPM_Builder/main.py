"""
Hecos HPM Builder
Version: 1.1.0
Author: Antonio Meloni

Strumento CLI ufficiale per generare chiavi, firmare crittograficamente, compilare e scompattare in modo sicuro i pacchetti .hpkg per l'ecosistema Hecos.
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
from modules.settings import load_config, CONFIG_FILE

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def print_header(title):
    clear_screen()
    print(f"{Fore.CYAN}{'=' * 60}{Style.RESET_ALL}")
    print(f" {Fore.WHITE}{Style.BRIGHT}Hecos HPM Builder{Style.RESET_ALL} {Fore.LIGHTBLACK_EX}v1.1.0 — by Antonio Meloni{Style.RESET_ALL}")
    print(f" {Fore.LIGHTBLACK_EX}Strumento ufficiale per la gestione dei pacchetti .hpkg{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'-' * 60}{Style.RESET_ALL}")
    print(f"   {Fore.WHITE}{Style.BRIGHT}{title}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'=' * 60}{Style.RESET_ALL}\n")

def main_menu():
    # Carica la configurazione all'avvio
    load_config()
    log_info("Avvio HPM Builder completato.")

    while True:
        print_header("Main Menu")
        print(f"1. [KEY]  Generate Keys {Fore.LIGHTBLACK_EX}(Crea coppia chiavi Ed25519){Style.RESET_ALL}")
        print(f"2. [NEW]  Scaffold New Package {Fore.LIGHTBLACK_EX}(Crea scheletro nuovo pacchetto){Style.RESET_ALL}")
        print(f"3. [BLD]  Validate & Build Package {Fore.LIGHTBLACK_EX}(Firma e impacchetta in .hpkg){Style.RESET_ALL}")
        print(f"4. [ALL]  Build All Packages {Fore.LIGHTBLACK_EX}(Compila tutti i sorgenti *_src){Style.RESET_ALL}")
        print(f"5. [CHK]  Inspect & Validate Package {Fore.LIGHTBLACK_EX}(Verifica manifest, firma e file){Style.RESET_ALL}")
        print(f"6. [EXT]  Extract / Unpack Package {Fore.LIGHTBLACK_EX}(Decomprime pacchetto .hpkg){Style.RESET_ALL}")
        print(f"7. [UNP]  Unpack All Packages {Fore.LIGHTBLACK_EX}(Decomprime tutti i .hpkg in cartelle *_src){Style.RESET_ALL}")
        print(f"0. [EXIT] Chiudi\n")
        
        print(f"{Fore.LIGHTBLACK_EX}Config File: {CONFIG_FILE}{Style.RESET_ALL}")
        choice = input(f"\n{Fore.YELLOW}Seleziona un'opzione:{Style.RESET_ALL} ").strip()
        
        print()
        if choice == '1':
            print_header("Key Generation")
            generate_key_pair()
            input(f"\n{Fore.LIGHTBLACK_EX}Premi Invio per tornare al menu...{Style.RESET_ALL}")
        elif choice == '2':
            print_header("Scaffold New Package")
            scaffold_package()
            input(f"\n{Fore.LIGHTBLACK_EX}Premi Invio per tornare al menu...{Style.RESET_ALL}")
        elif choice == '3':
            print_header("Validate & Build Package")
            build_package()
            input(f"\n{Fore.LIGHTBLACK_EX}Premi Invio per tornare al menu...{Style.RESET_ALL}")
        elif choice == '4':
            print_header("Build All Packages")
            from modules.builder import build_all_packages
            build_all_packages()
            input(f"\n{Fore.LIGHTBLACK_EX}Premi Invio per tornare al menu...{Style.RESET_ALL}")
        elif choice == '5':
            print_header("Inspect & Validate Package")
            inspect_package()
            input(f"\n{Fore.LIGHTBLACK_EX}Premi Invio per tornare al menu...{Style.RESET_ALL}")
        elif choice == '6':
            print_header("Extract / Unpack Package")
            unpack_package()
            input(f"\n{Fore.LIGHTBLACK_EX}Premi Invio per tornare al menu...{Style.RESET_ALL}")
        elif choice == '7':
            print_header("Unpack All Packages")
            from modules.builder import unpack_all_packages
            unpack_all_packages()
            input(f"\n{Fore.LIGHTBLACK_EX}Premi Invio per tornare al menu...{Style.RESET_ALL}")
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
