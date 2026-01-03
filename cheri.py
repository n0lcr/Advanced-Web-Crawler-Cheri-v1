#!/usr/bin/env python3
import re
import sys
import json
import argparse
import subprocess
import random
from urllib.parse import urljoin, urlparse, parse_qs, urlencode
from collections import defaultdict, deque
from datetime import datetime
import time
from typing import Set, Dict, List, Tuple, Optional
import requests
from bs4 import BeautifulSoup
from colorama import Fore, Style, init
import threading
import concurrent.futures
import psutil
import os
import xml.etree.ElementTree as ET
import gc
import math
from math import log2
import urllib3
import warnings

init(autoreset=True)

# SSL uyarılarını devre dışı bırak
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
warnings.filterwarnings('ignore')

def yuklenme_animasyonu(metin, sure=2.0):
    yukleme_metni = f"{metin}"
    uzunluk = len(yukleme_metni)
    animasyon = "£¢€\¶~^"
    animasyon_sayaci = 0
    zaman_sayaci = 0
    i = 0

    baslangic_zamani = time.time()

    while (time.time() - baslangic_zamani) < sure:
        time.sleep(0.030)
        metin_listesi = list(yukleme_metni)
        x = ord(metin_listesi[i])
        y = 0
        if x != 32 and x != 46:
            if x > 90:
                y = x-32
            else:
                y = x + 32
        metin_listesi[i] = chr(y)
        sonuc = ''
        for j in range(uzunluk):
            sonuc = sonuc + metin_listesi[j]
        sys.stdout.write("\r"+sonuc + animasyon[animasyon_sayaci])
        sys.stdout.flush()
        yukleme_metni = sonuc

        animasyon_sayaci = (animasyon_sayaci + 1) % 4
        i = (i + 1) % uzunluk
        zaman_sayaci = zaman_sayaci + 1

    sys.stdout.write('\r\033[K')

class WebTarayici:
    def __init__(self, hedef_url: str, maksimum_derinlik: int = 3, bekleme_suresi: float = 0.2,
                 zaman_asimi: int = 10, kullanici_araci: str = None, maksimum_thread: int = 30,
                 cikti_dosyasi: str = None, ozel_filtre: str = None, zaman_guvenlik_modu: bool = False,
                 tor_kullan: bool = False, sadece_https: bool = False, eposta_dosyasi: str = None,
                 endpoint_testi: bool = False, subfinder_kullan: bool = False, google_servisleri_gormezden_gel: bool = False,
                 method: str = 'GET', resim_dosyalari_atla: bool = False, taklit_modu: bool = False,
                 gorevlendirici: bool = False, sadece_hedef: bool = False, api_key_bul: bool = False,
                 param_dosyasi: str = None, disable_ssl: bool = False, 
                 max_content_size: int = 0):  # 0 = sınırsız
        # URL'yi normalize et (https:// ekle)
        if not hedef_url.startswith(('http://', 'https://')):
            hedef_url = f'https://{hedef_url}'
        
        self.hedef_url = hedef_url.rstrip('/')
        parsed_url = urlparse(self.hedef_url)
        self.domain = parsed_url.netloc
        self.maksimum_derinlik = maksimum_derinlik
        self.bekleme_suresi = bekleme_suresi
        self.max_content_size = max_content_size  # 0 = sınırsız
        
        # Thread ayarlarını düzelt - TOR değilken de thread kullan
        if tor_kullan:
            self.zaman_asimi = 40 if zaman_asimi == 10 else zaman_asimi
            self.maksimum_thread = min(maksimum_thread, 15)  # TOR için max 15 thread
            print(f"{Fore.YELLOW}[!] TOR modu aktif: Timeout={self.zaman_asimi}s, Threads={self.maksimum_thread}{Style.RESET_ALL}")
        else:
            self.zaman_asimi = zaman_asimi
            self.maksimum_thread = min(maksimum_thread, 50)  # Normal için max 50 thread

        self.cikti_dosyasi = cikti_dosyasi
        self.ozel_filtre = ozel_filtre
        self.zaman_guvenlik_modu = zaman_guvenlik_modu
        self.tor_kullan = tor_kullan
        self.sadece_https = sadece_https
        self.eposta_dosyasi = eposta_dosyasi
        self.endpoint_testi = endpoint_testi
        self.subfinder_kullan = subfinder_kullan
        self.google_servisleri_gormezden_gel = google_servisleri_gormezden_gel
        self.method = method.upper()
        self.resim_dosyalari_atla = resim_dosyalari_atla
        self.taklit_modu = taklit_modu
        self.gorevlendirici = gorevlendirici
        self.sadece_hedef = sadece_hedef
        self.api_key_bul = api_key_bul
        self.param_dosyasi = param_dosyasi
        self.disable_ssl = disable_ssl

        domain_parcalari = self.domain.split('.')
        if len(domain_parcalari) >= 2:
            self.taban_domain = '.'.join(domain_parcalari[-2:])
        else:
            self.taban_domain = self.domain

        self.ziyaret_edilen_url: Set[str] = set()
        self.ziyaret_edilen_domainler: Set[str] = set()
        self.ziyaret_edilecek = deque([(self.hedef_url, 0)])
        self.kilit = threading.Lock()
        
        # Semaphore'u thread sayısına göre ayarla
        self.sema = threading.Semaphore(min(50, self.maksimum_thread * 2))

        self.benzersiz_url_yollari: Set[str] = set()
        self.benzersiz_parametreler: Set[str] = set()

        self.baslangic_zamani = None
        self.hata_sayisi = 0
        self.istek_sayisi = 0
        self.son_durdurma_sayisi = 0
        self.son_taklit_degisimi = 0
        self.bulunan_api_anahtarlari = []
        self.bulunan_dinamik_parametreler = []

        self.MAX_URL = 50_000 if tor_kullan else 100_000

        if api_key_bul:
            self.api_anahtari_dosyasi = "apikey.txt"
        else:
            self.api_anahtari_dosyasi = None

        self.kritik_dosyasi = ""

        if self.cikti_dosyasi:
            self.kritik_dosyasi = f"kritik.{self.cikti_dosyasi}"
        else:
            self.kritik_dosyasi = "kritik.txt"

        self.kesfedilen_endpointler: Set[str] = set()
        self.kesfedilen_url: Set[str] = set()

        self.sonuclar = {
            'linkler': {'iç': [], 'dış': []},
            'api_endpointleri': [],
            'js_dosyalari': [],
            'formlar': [],
            'gizli_alanlar': [],
            'yorumlar': [],
            'cerezler': [],
            'yerel_depolama': [],
            'webpaket_parcalari': [],
            'kaynak_haritalari': [],
            'alt_domainler': [],
            'eposta_adresleri': [],
            'potansiyel_guvenlik_aciklari': [],
            'xml_dosyalari': [],
            'js_endpointleri': []
        }

        self.oturum = requests.Session()

        # SSL doğrulamasını devre dışı bırak
        if self.disable_ssl:
            self.oturum.verify = False
            print(f"{Fore.YELLOW}[!] SSL doğrulaması devre dışı bırakıldı (güvenli değil!){Style.RESET_ALL}")

        # TOR proxy ayarları
        if self.tor_kullan:
            tor_proxy = {
                'http': 'socks5h://127.0.0.1:9050',
                'https': 'socks5h://127.0.0.1:9050'
            }
            self.oturum.proxies = tor_proxy
            print(f"{Fore.GREEN}[+] TOR proxy aktif: {tor_proxy['http']}{Style.RESET_ALL}")

            # TOR bağlantısını test et
            if self.tor_baglanti_testi():
                print(f"{Fore.GREEN}[✓] TOR bağlantısı başarılı{Style.RESET_ALL}")
            else:
                print(f"{Fore.RED}[-] TOR bağlantısı başarısız! TOR servisi çalışıyor mu?{Style.RESET_ALL}")
                print(f"{Fore.YELLOW}[!] TOR olmadan devam ediliyor...{Style.RESET_ALL}")
                self.tor_kullan = False
                self.oturum.proxies = {}

        self.kullanici_araclari = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
            "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15",
        ]

        self.kabul_dilleri = [
            'en-US,en;q=0.9',
            'tr-TR,tr;q=0.9,en;q=0.8',
            'de-DE,de;q=0.9,en;q=0.8',
            'fr-FR,fr;q=0.9,en;q=0.8',
            'es-ES,es;q=0.9,en;q=0.8',
        ]

        self.kabul_sifrelemeleri = [
            'gzip, deflate, br',
            'gzip, deflate',
            'identity',
        ]

        self.basliklari_guncelle(kullanici_araci)

        # Google Drive ve Docs gibi servisleri daha spesifik hale getir
        self.google_paternleri = [
            r'^https?://(www\.)?google\.com/',
            r'^https?://fonts\.gstatic\.com/',
            r'^https?://ajax\.googleapis\.com/',
            r'^https?://www\.googletagmanager\.com/gtag/',
            r'^https?://www\.google-analytics\.com/',
            r'^https?://pagead2\.googlesyndication\.com/',
        ]
        
        # Drive ve Docs için özel kontrol - bunları atlama
        self.google_servis_patternleri = [
            r'^https?://(?:docs|drive|sheets|slides)\.google\.com/',
            r'^https?://mail\.google\.com/',
            r'^https?://accounts\.google\.com/',
            r'^https?://myaccount\.google\.com/',
        ]

        self.atlanacak_uzantilar = [
            '.css', '.jpg', '.jpeg', '.png', '.gif', '.svg', '.ico',
            '.woff', '.woff2', '.ttf', '.eot', '.otf',
            '.mp3', '.mp4', '.avi', '.mov', '.wmv',
            '.pdf', '.docx', '.xls', '.xlsx',
        ]

        # TÜM API KEY PATTERNLERİ (İstenilen tüm pattern'ler)
        self.api_key_patterns = {
            # === AWS ===
            'AWS_ACCESS_KEY_ID': re.compile(r'\bAKIA[0-9A-Z]{16}\b'),
            'AWS_SECRET_ACCESS_KEY': re.compile(r'\b[0-9a-zA-Z/+]{40}\b'),
            'AWS_SESSION_TOKEN': re.compile(r'\bFQoGZXIvYXdz[0-9a-zA-Z/+]{200,}\b'),
            
            # === GOOGLE ===
            'GOOGLE_API_KEY': re.compile(r'\bAIza[0-9A-Za-z\-_]{35}\b'),
            'GOOGLE_CLOUD_PLATFORM_KEY': re.compile(r'\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b'),
            'GOOGLE_OAUTH_ACCESS_TOKEN': re.compile(r'\bya29\.[0-9A-Za-z\-_]{100,}\b'),
            'GOOGLE_OAUTH_REFRESH_TOKEN': re.compile(r'\b1//[0-9a-zA-Z\-_]{50,}\b'),
            
            # === STRIPE (ÖDEME SİSTEMİ) ===
            'STRIPE_SECRET_KEY': re.compile(r'\bsk_(live|test)_[0-9a-zA-Z]{24}\b'),
            'STRIPE_PUBLIC_KEY': re.compile(r'\bpk_(live|test)_[0-9a-zA-Z]{24}\b'),
            'STRIPE_RESTRICTED_KEY': re.compile(r'\brk_(live|test)_[0-9a-zA-Z]{24}\b'),
            'STRIPE_WEBHOOK_SECRET': re.compile(r'\bwhsec_[0-9a-zA-Z]{24,}\b'),
            
            # === PAYPAL ===
            'PAYPAL_CLIENT_ID': re.compile(r'\bA[E-Z]{1}[0-9A-Z]{15}\b'),
            'PAYPAL_SECRET': re.compile(r'\bE[0-9A-Z]{79}\b'),
            'PAYPAL_ACCESS_TOKEN': re.compile(r'\baccess_token\$[0-9A-Z]{70,}\b'),
            
            # === SQUARE (FİNANSAL) ===
            'SQUARE_ACCESS_TOKEN': re.compile(r'\bsq0atp-[0-9A-Za-z\-_]{22,}\b'),
            'SQUARE_APPLICATION_ID': re.compile(r'\bsq0idp-[0-9A-Za-z\-_]{22,}\b'),
            
            # === TWILIO ===
            'TWILIO_ACCOUNT_SID': re.compile(r'\bAC[0-9a-fA-F]{32}\b'),
            'TWILIO_AUTH_TOKEN': re.compile(r'\b[0-9a-fA-F]{32}\b'),
            'TWILIO_API_KEY': re.compile(r'\bSK[0-9a-fA-F]{32}\b'),
            'TWILIO_API_SECRET': re.compile(r'\b[0-9a-fA-F]{32}\b'),
            
            # === SLACK ===
            'SLACK_BOT_TOKEN': re.compile(r'\bxoxb-[0-9]{12}-[0-9]{12}-[0-9a-zA-Z]{32}\b'),
            'SLACK_USER_TOKEN': re.compile(r'\bxoxp-[0-9]{12}-[0-9]{12}-[0-9a-zA-Z]{32}\b'),
            'SLACK_APP_TOKEN': re.compile(r'\bxapp-[0-9]-[0-9A-Z]{10,}\b'),
            'SLACK_LEGACY_TOKEN': re.compile(r'\bxoxs-[0-9a-zA-Z]{10,}\b'),
            'SLACK_WEBHOOK_URL': re.compile(r'https://hooks\.slack\.com/services/T[0-9A-Z]{9}/B[0-9A-Z]{9}/[0-9a-zA-Z]{24}\b'),
            
            # === GITHUB ===
            'GITHUB_PERSONAL_ACCESS_TOKEN': re.compile(r'\bghp_[0-9a-zA-Z]{36}\b'),
            'GITHUB_OAUTH_ACCESS_TOKEN': re.compile(r'\bgho_[0-9a-zA-Z]{36}\b'),
            'GITHUB_APP_INSTALLATION_TOKEN': re.compile(r'\bghs_[0-9a-zA-Z]{36}\b'),
            'GITHUB_REFRESH_TOKEN': re.compile(r'\bghr_[0-9a-zA-Z]{36}\b'),
            'GITHUB_FINE_GRAINED_TOKEN': re.compile(r'\bgithub_pat_[0-9a-zA-Z_]{22}_[0-9a-zA-Z_]{59}\b'),
            
            # === FACEBOOK ===
            'FACEBOOK_APP_ID': re.compile(r'\b[0-9]{15,16}\b'),
            'FACEBOOK_APP_SECRET': re.compile(r'\b[0-9a-f]{32}\b'),
            'FACEBOOK_ACCESS_TOKEN': re.compile(r'\bEAA[0-9a-zA-Z]{100,}\b'),
            'FACEBOOK_PAGE_ACCESS_TOKEN': re.compile(r'\bEAA[0-9a-zA-Z]{100,}\b'),
            
            # === TWITTER/X ===
            'TWITTER_API_KEY': re.compile(r'\b[0-9a-zA-Z]{25}\b'),
            'TWITTER_API_SECRET': re.compile(r'\b[0-9a-zA-Z]{50}\b'),
            'TWITTER_BEARER_TOKEN': re.compile(r'\bAAAAAAAAA[0-9a-zA-Z]{100,}\b'),
            'TWITTER_ACCESS_TOKEN': re.compile(r'\b[0-9]{19}-[0-9a-zA-Z]{40}\b'),
            'TWITTER_ACCESS_TOKEN_SECRET': re.compile(r'\b[0-9a-zA-Z]{45}\b'),
            
            # === LINKEDIN ===
            'LINKEDIN_CLIENT_ID': re.compile(r'\b[0-9a-zA-Z]{12}\b'),
            'LINKEDIN_CLIENT_SECRET': re.compile(r'\b[0-9a-zA-Z]{16}\b'),
            'LINKEDIN_ACCESS_TOKEN': re.compile(r'\bAQ[0-9a-zA-Z\-_]{100,}\b'),
            
            # === INSTAGRAM ===
            'INSTAGRAM_ACCESS_TOKEN': re.compile(r'\bIG[0-9a-zA-Z\.]{100,}\b'),
            'INSTAGRAM_APP_ID': re.compile(r'\b[0-9]{15,16}\b'),
            'INSTAGRAM_APP_SECRET': re.compile(r'\b[0-9a-f]{32}\b'),
            
            # === DISCORD ===
            'DISCORD_BOT_TOKEN': re.compile(r'\b[a-zA-Z0-9]{24}\.[a-zA-Z0-9]{6}\.[a-zA-Z0-9\-_]{27}\b'),
            'DISCORD_CLIENT_ID': re.compile(r'\b[0-9]{18}\b'),
            'DISCORD_CLIENT_SECRET': re.compile(r'\b[a-zA-Z0-9\-_]{32}\b'),
            
            # === TELEGRAM ===
            'TELEGRAM_BOT_TOKEN': re.compile(r'\b[0-9]{8,10}:[0-9a-zA-Z\-_]{35}\b'),
            'TELEGRAM_API_ID': re.compile(r'\b[0-9]{5,9}\b'),
            'TELEGRAM_API_HASH': re.compile(r'\b[0-9a-f]{32}\b'),
            
            # === MICROSOFT/AZURE ===
            'AZURE_SUBSCRIPTION_ID': re.compile(r'\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b'),
            'AZURE_TENANT_ID': re.compile(r'\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b'),
            'AZURE_CLIENT_ID': re.compile(r'\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b'),
            'AZURE_CLIENT_SECRET': re.compile(r'\b[0-9a-zA-Z\-_]{40,}\b'),
            'MICROSOFT_GRAPH_TOKEN': re.compile(r'\bEw[0-9a-zA-Z\-_]{800,}\b'),
            
            # === DROPBOX ===
            'DROPBOX_ACCESS_TOKEN': re.compile(r'\bsl\.[0-9a-zA-Z\-_]{100,}\b'),
            'DROPBOX_APP_KEY': re.compile(r'\b[0-9a-zA-Z]{15}\b'),
            'DROPBOX_APP_SECRET': re.compile(r'\b[0-9a-zA-Z]{15}\b'),
            
            # === HEROKU ===
            'HEROKU_API_KEY': re.compile(r'\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b'),
            'HEROKU_OAUTH_TOKEN': re.compile(r'\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b'),
            
            # === DIGITALOCEAN ===
            'DIGITALOCEAN_TOKEN': re.compile(r'\bdop_v1_[0-9a-f]{64}\b'),
            'DIGITALOCEAN_SPACES_KEY': re.compile(r'\b[0-9a-zA-Z]{20}\b'),
            'DIGITALOCEAN_SPACES_SECRET': re.compile(r'\b[0-9a-zA-Z/+]{40}\b'),
            
            # === SENDGRID ===
            'SENDGRID_API_KEY': re.compile(r'\bSG\.[0-9a-zA-Z\-_]{22}\.[0-9a-zA-Z\-_]{43}\b'),
            'SENDGRID_PASSWORD': re.compile(r'\b[0-9a-zA-Z\-_]{16,}\b'),
            
            # === MAILGUN ===
            'MAILGUN_API_KEY': re.compile(r'\bkey-[0-9a-zA-Z]{32}\b'),
            'MAILGUN_DOMAIN': re.compile(r'\b[0-9a-zA-Z\-_]{10,}\.mailgun\.org\b'),
            
            # === MAILCHIMP ===
            'MAILCHIMP_API_KEY': re.compile(r'\b[0-9a-f]{32}-us[0-9]{1,2}\b'),
            'MAILCHIMP_DC': re.compile(r'\bus[0-9]{1,2}\b'),
            
            # === MANDRILL (MAILCHIMP) ===
            'MANDRILL_API_KEY': re.compile(r'\b[a-zA-Z0-9\-_]{22,}\b'),
            
            # === POSTMARK ===
            'POSTMARK_SERVER_TOKEN': re.compile(r'\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b'),
            'POSTMARK_ACCOUNT_TOKEN': re.compile(r'\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b'),
            
            # === TWILIO SENDGRID ===
            'TWILIO_SENDGRID_API_KEY': re.compile(r'\bSG\.[0-9a-zA-Z\-_]{22}\.[0-9a-zA-Z\-_]{43}\b'),
            
            # === BRAINTREE (PAYPAL) ===
            'BRAINTREE_MERCHANT_ID': re.compile(r'\b[0-9a-zA-Z]{16}\b'),
            'BRAINTREE_PUBLIC_KEY': re.compile(r'\b[0-9a-zA-Z]{16}\b'),
            'BRAINTREE_PRIVATE_KEY': re.compile(r'\b[0-9a-f]{32}\b'),
            
            # === AUTHORIZE.NET ===
            'AUTHORIZE_API_LOGIN_ID': re.compile(r'\b[0-9a-zA-Z]{15}\b'),
            'AUTHORIZE_TRANSACTION_KEY': re.compile(r'\b[0-9a-zA-Z]{16}\b'),
            
            # === WORLDPAY ===
            'WORLDPAY_SERVICE_KEY': re.compile(r'\bT_S_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b'),
            'WORLDPAY_CLIENT_KEY': re.compile(r'\bT_C_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b'),
            
            # === ADYEN (ÖDEME) ===
            'ADYEN_API_KEY': re.compile(r'\bAQE[0-9a-zA-ZhmHM]{32,}\b'),
            'ADYEN_CLIENT_KEY': re.compile(r'\btest_[0-9a-zA-Z]{20,}\b'),
            
            # === CHECKOUT.COM ===
            'CHECKOUT_SECRET_KEY': re.compile(r'\bsk_(test|live)_[0-9a-zA-Z]{20,}\b'),
            'CHECKOUT_PUBLIC_KEY': re.compile(r'\bpk_(test|live)_[0-9a-zA-Z]{20,}\b'),
            
            # === RAPYD (FİNANSAL) ===
            'RAPYD_ACCESS_KEY': re.compile(r'\b[0-9a-f]{32}\b'),
            'RAPYD_SECRET_KEY': re.compile(r'\b[0-9a-f]{64}\b'),
            
            # === CURRENCIES DIRECT ===
            'CURRENCIES_DIRECT_API_KEY': re.compile(r'\bCD[0-9a-zA-Z]{20,}\b'),
            
            # === TRANSFERWISE (WISE) ===
            'WISE_API_TOKEN': re.compile(r'\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b'),
            
            # === REVOLUT ===
            'REVOLUT_API_KEY': re.compile(r'\brv_[0-9a-zA-Z]{40,}\b'),
            
            # === PAYONEER ===
            'PAYONEER_API_KEY': re.compile(r'\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b'),
            
            # === SKRILL ===
            'SKRILL_MERCHANT_ID': re.compile(r'\b[0-9]{6,10}\b'),
            'SKRILL_SECRET_WORD': re.compile(r'\b[0-9a-zA-Z]{10,20}\b'),
            
            # === NETELLER ===
            'NETELLER_CLIENT_ID': re.compile(r'\bCN[0-9]{10}\b'),
            'NETELLER_CLIENT_SECRET': re.compile(r'\bCS[0-9a-zA-Z]{20,}\b'),
            
            # === BITPAY ===
            'BITPAY_API_TOKEN': re.compile(r'\b[0-9a-zA-Z]{20,}\b'),
            
            # === COINBASE ===
            'COINBASE_API_KEY': re.compile(r'\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b'),
            'COINBASE_API_SECRET': re.compile(r'\b[0-9a-zA-Z/+]{40,}\b'),
            
            # === BINANCE ===
            'BINANCE_API_KEY': re.compile(r'\b[0-9a-zA-Z]{64}\b'),
            'BINANCE_SECRET_KEY': re.compile(r'\b[0-9a-zA-Z]{64}\b'),
            
            # === KRAKEN ===
            'KRAKEN_API_KEY': re.compile(r'\b[0-9a-zA-Z/+=]{80,}\b'),
            'KRAKEN_PRIVATE_KEY': re.compile(r'\b[0-9a-zA-Z/+=]{80,}\b'),
            
            # === BITSTAMP ===
            'BITSTAMP_API_KEY': re.compile(r'\b[0-9a-zA-Z]{32}\b'),
            'BITSTAMP_SECRET': re.compile(r'\b[0-9a-zA-Z]{64}\b'),
            
            # === OKX ===
            'OKX_API_KEY': re.compile(r'\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b'),
            'OKX_SECRET_KEY': re.compile(r'\b[0-9a-zA-Z]{40,}\b'),
            
            # === HUOBI ===
            'HUOBI_ACCESS_KEY': re.compile(r'\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b'),
            'HUOBI_SECRET_KEY': re.compile(r'\b[0-9a-zA-Z]{40,}\b'),
            
            # === BYBIT ===
            'BYBIT_API_KEY': re.compile(r'\b[0-9a-zA-Z]{20,}\b'),
            'BYBIT_SECRET_KEY': re.compile(r'\b[0-9a-zA-Z]{40,}\b'),
            
            # === FIREBASE ===
            'FIREBASE_API_KEY': re.compile(r'\bAIza[0-9A-Za-z\-_]{35}\b'),
            'FIREBASE_PROJECT_ID': re.compile(r'\b[a-z0-9\-]{6,30}\b'),
            'FIREBASE_SERVICE_ACCOUNT': re.compile(r'\b{"type":"service_account".{100,}\b'),
            
            # === ALGOLIA ===
            'ALGOLIA_API_KEY': re.compile(r'\b[0-9a-f]{32}\b'),
            'ALGOLIA_SEARCH_KEY': re.compile(r'\b[0-9a-f]{32}\b'),
            'ALGOLIA_ADMIN_KEY': re.compile(r'\b[0-9a-f]{32}\b'),
            
            # === ELASTICSEARCH ===
            'ELASTICSEARCH_API_KEY': re.compile(r'\b[0-9a-zA-Z\-_]{20,}\b'),
            
            # === ATLASSIAN ===
            'ATLASSIAN_API_TOKEN': re.compile(r'\batlassian-api-token-[0-9a-zA-Z]{40,}\b'),
            'JIRA_API_TOKEN': re.compile(r'\b[0-9a-zA-Z]{24}\b'),
            'CONFLUENCE_API_TOKEN': re.compile(r'\b[0-9a-zA-Z]{24}\b'),
            
            # === TRELLO ===
            'TRELLO_API_KEY': re.compile(r'\b[0-9a-f]{32}\b'),
            'TRELLO_API_TOKEN': re.compile(r'\b[0-9a-f]{64}\b'),
            
            # === ASANA ===
            'ASANA_ACCESS_TOKEN': re.compile(r'\b0\/[0-9a-f]{64}\b'),
            'ASANA_CLIENT_ID': re.compile(r'\b[0-9]{16}\b'),
            'ASANA_CLIENT_SECRET': re.compile(r'\b[0-9a-f]{64}\b'),
            
            # === ZOOM ===
            'ZOOM_JWT_TOKEN': re.compile(r'\beyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9\.[0-9a-zA-Z\-_]{100,}\.[0-9a-zA-Z\-_]{20,}\b'),
            'ZOOM_API_KEY': re.compile(r'\b[0-9a-zA-Z]{20,}\b'),
            'ZOOM_API_SECRET': re.compile(r'\b[0-9a-zA-Z]{40,}\b'),
            
            # === GOOGLE RECAPTCHA ===
            'RECAPTCHA_SITE_KEY': re.compile(r'\b6L[0-9a-zA-Z\-_]{20,40}\b'),
            'RECAPTCHA_SECRET_KEY': re.compile(r'\b6L[0-9a-zA-Z\-_]{20,40}\b'),
            
            # === CLOUDFLARE ===
            'CLOUDFLARE_API_KEY': re.compile(r'\b[0-9a-f]{37}\b'),
            'CLOUDFLARE_API_TOKEN': re.compile(r'\b[0-9a-zA-Z\-_]{40,}\b'),
            'CLOUDFLARE_ZONE_ID': re.compile(r'\b[0-9a-f]{32}\b'),
            
            # === AKAMAI ===
            'AKAMAI_ACCESS_TOKEN': re.compile(r'\bakab-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b'),
            'AKAMAI_CLIENT_TOKEN': re.compile(r'\b[0-9a-f]{64}\b'),
            
            # === FASTLY ===
            'FASTLY_API_TOKEN': re.compile(r'\b[0-9a-zA-Z]{32}\b'),
            
            # === DATADOG ===
            'DATADOG_API_KEY': re.compile(r'\b[0-9a-f]{32}\b'),
            'DATADOG_APPLICATION_KEY': re.compile(r'\b[0-9a-f]{40}\b'),
            
            # === NEW RELIC ===
            'NEW_RELIC_API_KEY': re.compile(r'\bNRAK-[0-9A-Z]{20,}\b'),
            'NEW_RELIC_INSERT_KEY': re.compile(r'\bNRII-[0-9a-zA-Z\-_]{20,}\b'),
            'NEW_RELIC_LICENSE_KEY': re.compile(r'\b[0-9a-f]{40}\b'),
            
            # === SENTRY ===
            'SENTRY_DSN': re.compile(r'\bhttps://[0-9a-f]{32}@[0-9]{1,3}\.ingest\.sentry\.io/[0-9]{1,6}\b'),
            'SENTRY_AUTH_TOKEN': re.compile(r'\bsntrys_[0-9a-zA-Z\-_]{40,}\b'),
            
            # === LOGGLY ===
            'LOGGLY_TOKEN': re.compile(r'\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b'),
            
            # === PAPERTRAIL ===
            'PAPERTRAIL_TOKEN': re.compile(r'\b[0-9a-zA-Z]{20,}\b'),
            
            # === SUMO LOGIC ===
            'SUMO_LOGIC_ACCESS_ID': re.compile(r'\b[0-9a-zA-Z]{20,}\b'),
            'SUMO_LOGIC_ACCESS_KEY': re.compile(r'\b[0-9a-zA-Z/+]{40,}\b'),
            
            # === HONEYBADGER ===
            'HONEYBADGER_API_KEY': re.compile(r'\bhb_[0-9a-zA-Z]{20,}\b'),
            
            # === BUGSNAG ===
            'BUGSNAG_API_KEY': re.compile(r'\b[0-9a-f]{32}\b'),
            
            # === ROLLBAR ===
            'ROLLBAR_ACCESS_TOKEN': re.compile(r'\b[0-9a-f]{32}\b'),
            'ROLLBAR_POST_SERVER_ITEM': re.compile(r'\b[0-9a-f]{32}\b'),
            
            # === AIRBRAKE ===
            'AIRBRAKE_API_KEY': re.compile(r'\b[0-9a-f]{32}\b'),
            
            # === OPENAI ===
            'OPENAI_API_KEY': re.compile(r'\bsk-[0-9a-zA-Z]{48}\b'),
            'OPENAI_ORGANIZATION': re.compile(r'\borg-[0-9a-zA-Z]{24}\b'),
            
            # === ANTHROPIC (CLAUDE) ===
            'ANTHROPIC_API_KEY': re.compile(r'\bsk-ant-[0-9a-zA-Z\-_]{40,}\b'),
            
            # === COHERE ===
            'COHERE_API_KEY': re.compile(r'\b[0-9a-zA-Z]{40}\b'),
            
            # === HUGGINGFACE ===
            'HUGGINGFACE_TOKEN': re.compile(r'\bhf_[0-9a-zA-Z]{34}\b'),
            
            # === REPLICATE ===
            'REPLICATE_API_TOKEN': re.compile(r'\br8_[0-9a-zA-Z]{37}\b'),
            
            # === STABILITY AI ===
            'STABILITY_AI_KEY': re.compile(r'\bsk-[0-9a-zA-Z]{48}\b'),
            
            # === MIDJOURNEY ===
            'MIDJOURNEY_API_KEY': re.compile(r'\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b'),
            
            # === ELEVENLABS ===
            'ELEVENLABS_API_KEY': re.compile(r'\b[0-9a-f]{32}\b'),
            
            # === SPOTIFY ===
            'SPOTIFY_CLIENT_ID': re.compile(r'\b[0-9a-f]{32}\b'),
            'SPOTIFY_CLIENT_SECRET': re.compile(r'\b[0-9a-f]{32}\b'),
            'SPOTIFY_ACCESS_TOKEN': re.compile(r'\bBQA[0-9a-zA-Z\-_]{100,}\b'),
            
            # === SOUNDCLOUD ===
            'SOUNDCLOUD_CLIENT_ID': re.compile(r'\b[0-9a-zA-Z]{32}\b'),
            'SOUNDCLOUD_CLIENT_SECRET': re.compile(r'\b[0-9a-zA-Z]{32}\b'),
            
            # === YOUTUBE ===
            'YOUTUBE_API_KEY': re.compile(r'\bAIza[0-9A-Za-z\-_]{35}\b'),
            
            # === VIMEO ===
            'VIMEO_ACCESS_TOKEN': re.compile(r'\b[0-9a-f]{64}\b'),
            
            # === TWITCH ===
            'TWITCH_CLIENT_ID': re.compile(r'\b[0-9a-zA-Z]{30}\b'),
            'TWITCH_CLIENT_SECRET': re.compile(r'\b[0-9a-zA-Z]{30}\b'),
            'TWITCH_ACCESS_TOKEN': re.compile(r'\b[0-9a-zA-Z]{30}\b'),
            
            # === MAPBOX ===
            'MAPBOX_ACCESS_TOKEN': re.compile(r'\bpk\.[0-9a-zA-Z\-_]{100,}\b'),
            'MAPBOX_SECRET_TOKEN': re.compile(r'\bsk\.[0-9a-zA-Z\-_]{100,}\b'),
            
            # === GOOGLE MAPS ===
            'GOOGLE_MAPS_API_KEY': re.compile(r'\bAIza[0-9A-Za-z\-_]{35}\b'),
            
            # === HERE ===
            'HERE_API_KEY': re.compile(r'\b[0-9a-zA-Z\-_]{40,}\b'),
            
            # === TOMTOM ===
            'TOMTOM_API_KEY': re.compile(r'\b[0-9a-zA-Z\-_]{20,}\b'),
            
            # === IPINFO ===
            'IPINFO_TOKEN': re.compile(r'\b[0-9a-f]{32}\b'),
            
            # === IPSTACK ===
            'IPSTACK_ACCESS_KEY': re.compile(r'\b[0-9a-f]{32}\b'),
            
            # === ABSTRACT API ===
            'ABSTRACT_API_KEY': re.compile(r'\b[0-9a-f]{32}\b'),
            
            # === POSITIONSTACK ===
            'POSITIONSTACK_ACCESS_KEY': re.compile(r'\b[0-9a-f]{32}\b'),
            
            # === OPENWEATHERMAP ===
            'OPENWEATHERMAP_API_KEY': re.compile(r'\b[0-9a-f]{32}\b'),
            
            # === WEATHERSTACK ===
            'WEATHERSTACK_API_KEY': re.compile(r'\b[0-9a-f]{32}\b'),
            
            # === ACCUWEATHER ===
            'ACCUWEATHER_API_KEY': re.compile(r'\b[0-9a-zA-Z]{32}\b'),
            
            # === NASA ===
            'NASA_API_KEY': re.compile(r'\b[0-9a-zA-Z]{40}\b'),
            
            # === NEWS API ===
            'NEWS_API_KEY': re.compile(r'\b[0-9a-f]{32}\b'),
            
            # === GNEWS ===
            'GNEWS_API_KEY': re.compile(r'\b[0-9a-f]{32}\b'),
            
            # === REDDIT ===
            'REDDIT_CLIENT_ID': re.compile(r'\b[0-9a-zA-Z]{14}\b'),
            'REDDIT_CLIENT_SECRET': re.compile(r'\b[0-9a-zA-Z]{27}\b'),
            'REDDIT_ACCESS_TOKEN': re.compile(r'\b[0-9a-zA-Z\-_]{40,}\b'),
            
            # === PINTEREST ===
            'PINTEREST_ACCESS_TOKEN': re.compile(r'\b[0-9a-f]{64}\b'),
            
            # === TIKTOK ===
            'TIKTOK_ACCESS_TOKEN': re.compile(r'\b[0-9a-f]{64}\b'),
            'TIKTOK_CLIENT_KEY': re.compile(r'\b[0-9a-zA-Z]{20,}\b'),
            'TIKTOK_CLIENT_SECRET': re.compile(r'\b[0-9a-zA-Z]{40,}\b'),
            
            # === SNAPCHAT ===
            'SNAPCHAT_CLIENT_ID': re.compile(r'\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b'),
            'SNAPCHAT_CLIENT_SECRET': re.compile(r'\b[0-9a-zA-Z]{40,}\b'),
            
            # === WHATSAPP BUSINESS ===
            'WHATSAPP_ACCESS_TOKEN': re.compile(r'\bEAA[0-9a-zA-Z]{100,}\b'),
            'WHATSAPP_PHONE_NUMBER_ID': re.compile(r'\b[0-9]{15,}\b'),
            
            # === LINE ===
            'LINE_CHANNEL_ACCESS_TOKEN': re.compile(r'\b[0-9a-zA-Z\-_]{100,}\b'),
            'LINE_CHANNEL_SECRET': re.compile(r'\b[0-9a-f]{32}\b'),
            
            # === WECHAT ===
            'WECHAT_APP_ID': re.compile(r'\b[0-9a-zA-Z]{18}\b'),
            'WECHAT_APP_SECRET': re.compile(r'\b[0-9a-f]{32}\b'),
            
            # === VK ===
            'VK_ACCESS_TOKEN': re.compile(r'\b[0-9a-f]{85}\b'),
            'VK_SERVICE_TOKEN': re.compile(r'\b[0-9a-f]{85}\b'),
            
            # === ODNOKLASSNIKI ===
            'ODNOKLASSNIKI_ACCESS_TOKEN': re.compile(r'\btkn[0-9a-zA-Z]{80,}\b'),
            
            # === NODEJS ===
            'NODE_ENV_SECRET': re.compile(r'\bprocess\.env\.[A-Z_]+=["\']([^"\']{20,})["\']'),
            
            # === DJANGO ===
            'DJANGO_SECRET_KEY': re.compile(r'\bSECRET_KEY\s*=\s*["\']([0-9a-zA-Z!@#$%^&*()_+\-=\[\]{}|;:,.<>?/~`]{50,})["\']'),
            
            # === RAILS ===
            'RAILS_SECRET_KEY_BASE': re.compile(r'\bSECRET_KEY_BASE\s*=\s*([0-9a-f]{128})'),
            
            # === LARAVEL ===
            'LARAVEL_APP_KEY': re.compile(r'\bAPP_KEY\s*=\s*base64:([0-9a-zA-Z+/=]{40,})'),
            
            # === EXPRESS/SESSION ===
            'EXPRESS_SESSION_SECRET': re.compile(r'\bsessionSecret\s*:\s*["\']([^"\']{20,})["\']'),
            
            # === FLASK ===
            'FLASK_SECRET_KEY': re.compile(r'\bSECRET_KEY\s*=\s*["\']([^"\']{20,})["\']'),
            
            # === SYMFONY ===
            'SYMFONY_APP_SECRET': re.compile(r'\bAPP_SECRET\s*=\s*([0-9a-f]{32})'),
            
            # === WORDPRESS ===
            'WORDPRESS_AUTH_KEY': re.compile(r'\bdefine\(\s*["\']AUTH_KEY["\']\s*,\s*["\']([^"\']{50,})["\']'),
            'WORDPRESS_SECURE_AUTH_KEY': re.compile(r'\bdefine\(\s*["\']SECURE_AUTH_KEY["\']\s*,\s*["\']([^"\']{50,})["\']'),
            'WORDPRESS_LOGGED_IN_KEY': re.compile(r'\bdefine\(\s*["\']LOGGED_IN_KEY["\']\s*,\s*["\']([^"\']{50,})["\']'),
            'WORDPRESS_NONCE_KEY': re.compile(r'\bdefine\(\s*["\']NONCE_KEY["\']\s*,\s*["\']([^"\']{50,})["\']'),
            
            # === JOOMLA ===
            'JOOMLA_SECRET': re.compile(r'\bpublic\s+\$secret\s*=\s*["\']([^"\']{32})["\']'),
            
            # === DRUPAL ===
            'DRUPAL_PRIVATE_KEY': re.compile(r'\b\$settings\[["\']hash_salt["\']\]\s*=\s*["\']([^"\']{50,})["\']'),
            
            # === MAGENTO ===
            'MAGENTO_CRYPT_KEY': re.compile(r'\b<crypt_key><!\[CDATA\[([0-9a-f]{32})\]\]></crypt_key>'),
            
            # === PRESTASHOP ===
            'PRESTASHOP_COOKIE_KEY': re.compile(r'\bdefine\(\s*["\']_COOKIE_KEY_["\']\s*,\s*["\']([0-9a-f]{32})["\']'),
            
            # === WOOCOMMERCE ===
            'WOOCOMMERCE_CONSUMER_KEY': re.compile(r'\bck_[0-9a-f]{32}\b'),
            'WOOCOMMERCE_CONSUMER_SECRET': re.compile(r'\bcs_[0-9a-f]{32}\b'),
            
            # === SHOPIFY ===
            'SHOPIFY_ACCESS_TOKEN': re.compile(r'\bshpss_[0-9a-f]{32}\b'),
            'SHOPIFY_PRIVATE_APP_PASSWORD': re.compile(r'\b[0-9a-f]{32}\b'),
            'SHOPIFY_SHARED_SECRET': re.compile(r'\b[0-9a-f]{32}\b'),
            
            # === BIGCOMMERCE ===
            'BIGCOMMERCE_ACCESS_TOKEN': re.compile(r'\b[0-9a-f]{32}\b'),
            'BIGCOMMERCE_CLIENT_ID': re.compile(r'\b[0-9a-f]{32}\b'),
            'BIGCOMMERCE_CLIENT_SECRET': re.compile(r'\b[0-9a-f]{32}\b'),
            
            # === SQUARESPACE ===
            'SQUARESPACE_ACCESS_TOKEN': re.compile(r'\b[0-9a-f]{64}\b'),
            
            # === WIX ===
            'WIX_API_KEY': re.compile(r'\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b'),
            
            # === WEBFLOW ===
            'WEBFLOW_API_TOKEN': re.compile(r'\b[0-9a-f]{64}\b'),
            
            # === CONTENTFUL ===
            'CONTENTFUL_ACCESS_TOKEN': re.compile(r'\b[0-9a-zA-Z\-_]{40,}\b'),
            'CONTENTFUL_MANAGEMENT_TOKEN': re.compile(r'\bCFPAT-[0-9a-zA-Z\-_]{40,}\b'),
            
            # === SANITY ===
            'SANITY_API_TOKEN': re.compile(r'\bsk[0-9a-zA-Z\-_]{40,}\b'),
            'SANITY_PROJECT_ID': re.compile(r'\b[0-9a-z]{8}\b'),
            
            # === STRAPI ===
            'STRAPI_ADMIN_JWT': re.compile(r'\beyJ[0-9a-zA-Z\-_]{100,}\.[0-9a-zA-Z\-_]{100,}\.[0-9a-zA-Z\-_]{20,}\b'),
            
            # === DIRECTUS ===
            'DIRECTUS_TOKEN': re.compile(r'\b[0-9a-f]{64}\b'),
            
            # === PRISMA ===
            'PRISMA_DATABASE_URL': re.compile(r'\bpostgresql://[^:]+:[^@]+@[^/]+/[^?]+\b'),
            
            # === HASURA ===
            'HASURA_ADMIN_SECRET': re.compile(r'\b[0-9a-zA-Z\-_]{20,}\b'),
            
            # === GRAPHQL ===
            'GRAPHQL_TOKEN': re.compile(r'\bBearer\s+[0-9a-zA-Z\-_]{100,}\b'),
            
            # === JWT ===
            'JWT_TOKEN': re.compile(r'\beyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9\.[0-9a-zA-Z\-_]+?\.[0-9a-zA-Z\-_]{20,}\b'),
            
            # === OAUTH2 ===
            'OAUTH2_ACCESS_TOKEN': re.compile(r'\baccess_token=[0-9a-zA-Z\-_\.]{20,100}\b'),
            'OAUTH2_REFRESH_TOKEN': re.compile(r'\brefresh_token=[0-9a-zA-Z\-_\.]{20,100}\b'),
            
            # === SAML ===
            'SAML_CERTIFICATE': re.compile(r'-----BEGIN CERTIFICATE-----[0-9a-zA-Z+/=\s]{100,}-----END CERTIFICATE-----'),
            
            # === OPENID ===
            'OPENID_CLIENT_SECRET': re.compile(r'\b[0-9a-zA-Z\-_]{20,}\b'),
            
            # === LDAP ===
            'LDAP_BIND_PASSWORD': re.compile(r'\bbind_password=["\']([^"\']{10,})["\']'),
            
            # === SSH ===
            'SSH_PRIVATE_KEY': re.compile(r'-----BEGIN (RSA|DSA|EC|OPENSSH) PRIVATE KEY-----[0-9a-zA-Z+/=\s]{100,}-----END (RSA|DSA|EC|OPENSSH) PRIVATE KEY-----'),
            
            # === SSL/TLS ===
            'SSL_PRIVATE_KEY': re.compile(r'-----BEGIN PRIVATE KEY-----[0-9a-zA-Z+/=\s]{100,}-----END PRIVATE KEY-----'),
            'SSL_CERTIFICATE': re.compile(r'-----BEGIN CERTIFICATE-----[0-9a-zA-Z+/=\s]{100,}-----END CERTIFICATE-----'),
            
            # === PGP/GPG ===
            'PGP_PRIVATE_KEY': re.compile(r'-----BEGIN PGP PRIVATE KEY BLOCK-----[0-9a-zA-Z+/=\s\n]{100,}-----END PGP PRIVATE KEY BLOCK-----'),
            'GPG_PRIVATE_KEY': re.compile(r'-----BEGIN PGP PRIVATE KEY BLOCK-----[0-9a-zA-Z+/=\s\n]{100,}-----END PGP PRIVATE KEY BLOCK-----'),
            
            # === DATABASE ===
            'MYSQL_CONNECTION_STRING': re.compile(r'\bmysql://[^:]+:[^@]+@[^/]+/[^?]+\b'),
            'POSTGRES_CONNECTION_STRING': re.compile(r'\bpostgres(ql)?://[^:]+:[^@]+@[^/]+/[^?]+\b'),
            'MONGODB_CONNECTION_STRING': re.compile(r'\bmongodb(\\+srv)?://[^:]+:[^@]+@[^/]+/[^?]+\b'),
            'REDIS_CONNECTION_STRING': re.compile(r'\bredis://[^:]+:[^@]+@[^/]+/[^?]+\b'),
            
            # === CLOUD DATABASES ===
            'SUPABASE_URL': re.compile(r'\bhttps://[0-9a-z]+\.supabase\.co\b'),
            'SUPABASE_KEY': re.compile(r'\beyJ[0-9a-zA-Z\-_]{100,}\.[0-9a-zA-Z\-_]{100,}\b'),
            
            # === AUTH0 ===
            'AUTH0_CLIENT_ID': re.compile(r'\b[0-9a-zA-Z]{20,}\b'),
            'AUTH0_CLIENT_SECRET': re.compile(r'\b[0-9a-zA-Z\-_]{40,}\b'),
            'AUTH0_DOMAIN': re.compile(r'\b[a-z0-9\-]+\.auth0\.com\b'),
            
            # === OKTA ===
            'OKTA_API_TOKEN': re.compile(r'\b[0-9a-zA-Z\-_]{40,}\b'),
            'OKTA_CLIENT_ID': re.compile(r'\b[0-9a-zA-Z]{20,}\b'),
            'OKTA_CLIENT_SECRET': re.compile(r'\b[0-9a-zA-Z\-_]{40,}\b'),
            
            # === COGNITO ===
            'COGNITO_CLIENT_ID': re.compile(r'\b[0-9a-z]{26}\b'),
            'COGNITO_CLIENT_SECRET': re.compile(r'\b[0-9a-zA-Z\-_]{40,}\b'),
            'COGNITO_USER_POOL_ID': re.compile(r'\bus-east-1_[0-9a-zA-Z]{10}\b'),
            
            # === KEYCLOAK ===
            'KEYCLOAK_CLIENT_SECRET': re.compile(r'\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b'),
            
            # === FUSIONAUTH ===
            'FUSIONAUTH_API_KEY': re.compile(r'\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b'),
            
            # === CURSFORCE ===
            'CURSFORCE_API_KEY': re.compile(r'\bcf_[0-9a-zA-Z]{32}\b'),
            'CURSFORCE_SECRET_KEY': re.compile(r'\bcf_sec_[0-9a-zA-Z]{64}\b'),
            'CURSFORCE_ACCESS_TOKEN': re.compile(r'\bcf_tok_[0-9a-zA-Z\-_]{40,}\b'),
            
            # === TÜRKİYE BANKALARI VE FİNANS KURUMLARI ===
            # Ziraat Bankası
            'ZIRAAT_API_KEY': re.compile(r'\bzb_[0-9a-f]{32}\b'),
            'ZIRAAT_MERCHANT_ID': re.compile(r'\bZR[0-9]{10}\b'),
            
            # İş Bankası
            'ISBANK_API_KEY': re.compile(r'\bisb_[0-9a-zA-Z]{24}\b'),
            'ISBANK_CLIENT_SECRET': re.compile(r'\bisb_sec_[0-9a-f]{40}\b'),
            
            # Garanti BBVA
            'GARANTI_API_KEY': re.compile(r'\bgar_[0-9a-zA-Z]{28}\b'),
            'GARANTI_TERMINAL_ID': re.compile(r'\bG[0-9]{8}\b'),
            'GARANTI_MERCHANT_ID': re.compile(r'\b[0-9]{8}\b'),
            
            # Yapı Kredi
            'YAPIKREDI_API_KEY': re.compile(r'\byk_[0-9a-f]{32}\b'),
            'YAPIKREDI_POS_ID': re.compile(r'\bP[0-9]{9}\b'),
            
            # Akbank
            'AKBANK_API_KEY': re.compile(r'\bakb_[0-9a-zA-Z]{20}\b'),
            'AKBANK_CLIENT_ID': re.compile(r'\bAKB[0-9]{10}\b'),
            
            # QNB Finansbank
            'QNB_API_KEY': re.compile(r'\bqnb_[0-9a-f]{36}\b'),
            'QNB_MERCHANT_CODE': re.compile(r'\bQN[0-9]{8}\b'),
            
            # Halkbank
            'HALKBANK_API_KEY': re.compile(r'\bhb_[0-9a-zA-Z]{24}\b'),
            'HALKBANK_TERMINAL_ID': re.compile(r'\bH[0-9]{7}\b'),
            
            # VakıfBank
            'VAKIFBANK_API_KEY': re.compile(r'\bvf_[0-9a-f]{28}\b'),
            'VAKIFBANK_MERCHANT_ID': re.compile(r'\bVF[0-9]{9}\b'),
            
            # DenizBank
            'DENIZBANK_API_KEY': re.compile(r'\bdb_[0-9a-zA-Z]{20}\b'),
            'DENIZBANK_POS_NUMBER': re.compile(r'\bD[0-9]{10}\b'),
            
            # Şekerbank
            'SEKERBANK_API_KEY': re.compile(r'\bsb_[0-9a-f]{24}\b'),
            
            # Anadolubank
            'ANADOLUBANK_API_KEY': re.compile(r'\bab_[0-9a-zA-Z]{22}\b'),
            
            # Fibabanka
            'FIBABANKA_API_KEY': re.compile(r'\bfb_[0-9a-f]{30}\b'),
            
            # Türk Ekonomi Bankası (TEB)
            'TEB_API_KEY': re.compile(r'\bteb_[0-9a-zA-Z]{26}\b'),
            'TEB_MERCHANT_ID': re.compile(r'\bTEB[0-9]{8}\b'),
            
            # ING Bank
            'INGBANK_API_KEY': re.compile(r'\bing_[0-9a-f]{32}\b'),
            
            # Odeabank
            'ODEABANK_API_KEY': re.compile(r'\boda_[0-9a-zA-Z]{20}\b'),
            
            # HSBC
            'HSBC_API_KEY': re.compile(r'\bhsbc_[0-9a-f]{28}\b'),
            'HSBC_CLIENT_ID': re.compile(r'\bHS[0-9]{10}\b'),
            
            # Citibank
            'CITIBANK_API_KEY': re.compile(r'\bciti_[0-9a-zA-Z]{24}\b'),
            
            # Burgan Bank
            'BURGANBANK_API_KEY': re.compile(r'\bbg_[0-9a-f]{26}\b'),
            
            # Türkiye Finans
            'TURKIYE_FINANS_API_KEY': re.compile(r'\btf_[0-9a-zA-Z]{22}\b'),
            
            # Albaraka Türk
            'ALBARAKA_API_KEY': re.compile(r'\balt_[0-9a-f]{30}\b'),
            
            # Kuveyt Türk
            'KUVEYT_TURK_API_KEY': re.compile(r'\bkt_[0-9a-zA-Z]{24}\b'),
            'KUVEYT_TURK_MERCHANT_ID': re.compile(r'\bKT[0-9]{9}\b'),
            
            # Ziraat Katılım
            'ZIRAAT_KATILIM_API_KEY': re.compile(r'\bzk_[0-9a-f]{28}\b'),
            
            # Vakıf Katılım
            'VAKIF_KATILIM_API_KEY': re.compile(r'\bvk_[0-9a-zA-Z]{24}\b'),
            
            # Emlak Katılım
            'EMLAK_KATILIM_API_KEY': re.compile(r'\bek_[0-9a-f]{26}\b'),
            
            # Türkiye İş Bankası (İşCep)
            'ISCEP_API_KEY': re.compile(r'\bisc_[0-9a-zA-Z]{32}\b'),
            
            # Enpara
            'ENPARA_API_KEY': re.compile(r'\benp_[0-9a-f]{30}\b'),
            
            # Papara
            'PAPARA_API_KEY': re.compile(r'\bppr_[0-9a-zA-Z]{40}\b'),
            'PAPARA_MERCHANT_ID': re.compile(r'\b[0-9]{10}\b'),
            
            # İyzico
            'IYZICO_API_KEY': re.compile(r'\biyz_[0-9a-zA-Z]{20}\b'),
            'IYZICO_SECRET_KEY': re.compile(r'\biyz_sec_[0-9a-f]{40}\b'),
            
            # PayTR
            'PAYTR_MERCHANT_ID': re.compile(r'\b[0-9]{6}\b'),
            'PAYTR_MERCHANT_KEY': re.compile(r'\b[0-9a-f]{32}\b'),
            'PAYTR_MERCHANT_SALT': re.compile(r'\b[0-9a-f]{32}\b'),
            
            # BKM Express
            'BKM_EXPRESS_TOKEN': re.compile(r'\bbkm_[0-9a-zA-Z]{36}\b'),
            
            # Troy
            'TROY_API_KEY': re.compile(r'\btry_[0-9a-f]{28}\b'),
            
            # Maximum
            'MAXIMUM_API_KEY': re.compile(r'\bmax_[0-9a-zA-Z]{24}\b'),
            
            # Bonus
            'BONUS_API_KEY': re.compile(r'\bbns_[0-9a-f]{30}\b'),
            
            # World
            'WORLD_API_KEY': re.compile(r'\bwrd_[0-9a-zA-Z]{22}\b'),
            
            # CardFinans
            'CARDFINANS_API_KEY': re.compile(r'\bcfn_[0-9a-f]{32}\b'),
            
            # Finansbank
            'FINANSBANK_API_KEY': re.compile(r'\bfnb_[0-9a-zA-Z]{20}\b'),
            
            # TEB POS
            'TEB_POS_API_KEY': re.compile(r'\btebpos_[0-9a-f]{36}\b'),
            
            # Yapı Kredi PayFor
            'YK_PAYFOR_API_KEY': re.compile(r'\bykpf_[0-9a-zA-Z]{40}\b'),
            
            # Güncel Ödeme Sistemleri
            'PAYU_API_KEY': re.compile(r'\bpayu_[0-9a-f]{32}\b'),
            'PAYU_MERCHANT_ID': re.compile(r'\b[0-9]{8}\b'),
            
            'MOBİLEXPRESS_API_KEY': re.compile(r'\bmexp_[0-9a-zA-Z]{28}\b'),
            
            'PAYCELL_API_KEY': re.compile(r'\bpayc_[0-9a-f]{30}\b'),
            
            # Türk Telekom
            'TURKTELEKOM_API_KEY': re.compile(r'\btt_[0-9a-zA-Z]{24}\b'),
            
            # Vodafone
            'VODAFONE_API_KEY': re.compile(r'\bvf_[0-9a-f]{32}\b'),
            
            # Turkcell
            'TURKCELL_API_KEY': re.compile(r'\btc_[0-9a-zA-Z]{26}\b'),
            
            # TTNET
            'TTNET_API_KEY': re.compile(r'\bttn_[0-9a-f]{28}\b'),
            
            # E-Devlet
            'EDEVLET_API_KEY': re.compile(r'\bed_[0-9a-f]{40}\b'),
            'EDEVLET_CLIENT_ID': re.compile(r'\bED[0-9]{12}\b'),
            
            # MERNIS
            'MERNIS_API_KEY': re.compile(r'\bmrs_[0-9a-zA-Z]{32}\b'),
            
            # SGK
            'SGK_API_KEY': re.compile(r'\bsgk_[0-9a-f]{36}\b'),
            
            # Vergi Dairesi
            'VD_API_KEY': re.compile(r'\bvd_[0-9a-zA-Z]{28}\b'),
            
            # TÜBİTAK
            'TUBITAK_API_KEY': re.compile(r'\btbt_[0-9a-f]{34}\b'),
            
            # ASELSAN
            'ASELSAN_API_KEY': re.compile(r'\basl_[0-9a-zA-Z]{30}\b'),
            
            # HAVELSAN
            'HAVELSAN_API_KEY': re.compile(r'\bhvl_[0-9a-f]{32}\b'),
            
            # ROKETSAN
            'ROKETSAN_API_KEY': re.compile(r'\brkt_[0-9a-zA-Z]{28}\b'),
            
            # TAI
            'TAI_API_KEY': re.compile(r'\btai_[0-9a-f]{30}\b'),
            
            # BMC
            'BMC_API_KEY': re.compile(r'\bbmc_[0-9a-zA-Z]{24}\b'),
            
            # FNSS
            'FNSS_API_KEY': re.compile(r'\bfnss_[0-9a-f]{32}\b'),
            
            # NUROL
            'NUROL_API_KEY': re.compile(r'\bnrl_[0-9a-zA-Z]{26}\b'),
            
            # OTOKAR
            'OTOKAR_API_KEY': re.compile(r'\botk_[0-9a-f]{28}\b'),
            
            # KOC HOLDING
            'KOC_API_KEY': re.compile(r'\bkoc_[0-9a-zA-Z]{30}\b'),
            
            # SABANCI
            'SABANCI_API_KEY': re.compile(r'\bsbc_[0-9a-f]{32}\b'),
            
            # DOĞUŞ
            'DOGUS_API_KEY': re.compile(r'\bdgs_[0-9a-zA-Z]{28}\b'),
            
            # Eczacıbaşı
            'ECZACIBASI_API_KEY': re.compile(r'\becz_[0-9a-f]{30}\b'),
            
            # ANATOLIAN
            'ANATOLIAN_API_KEY': re.compile(r'\bant_[0-9a-zA-Z]{26}\b'),
            
            # TRENDYOL
            'TRENDYOL_API_KEY': re.compile(r'\bty_[0-9a-f]{40}\b'),
            'TRENDYOL_SELLER_ID': re.compile(r'\b[0-9]{9}\b'),
            
            # HEPSİBURADA
            'HEPSIBURADA_API_KEY': re.compile(r'\bhb_[0-9a-f]{36}\b'),
            'HEPSIBURADA_MERCHANT_ID': re.compile(r'\b[0-9]{8}\b'),
            
            # N11
            'N11_API_KEY': re.compile(r'\bn11_[0-9a-zA-Z]{32}\b'),
            
            # GİTTİGİDİYOR
            'GITTIGIDIYOR_API_KEY': re.compile(r'\bgg_[0-9a-f]{34}\b'),
            
            # ÇİÇEKSEPETİ
            'CICEKSEPETI_API_KEY': re.compile(r'\bcs_[0-9a-zA-Z]{30}\b'),
            
            # YEMEKSEPETİ
            'YEMEKSEPETI_API_KEY': re.compile(r'\bys_[0-9a-f]{38}\b'),
            
            # GETİR
            'GETIR_API_KEY': re.compile(r'\bgtr_[0-9a-zA-Z]{32}\b'),
            
            # BİM
            'BIM_API_KEY': re.compile(r'\bbim_[0-9a-f]{28}\b'),
            
            # MİGROS
            'MIGROS_API_KEY': re.compile(r'\bmgr_[0-9a-zA-Z]{26}\b'),
            
            # A101
            'A101_API_KEY': re.compile(r'\ba101_[0-9a-f]{30}\b'),
            
            # ŞOK
            'SOK_API_KEY': re.compile(r'\bsok_[0-9a-zA-Z]{24}\b'),
            
            # CARREFOURSA
            'CARREFOURSA_API_KEY': re.compile(r'\bcfs_[0-9a-f]{32}\b'),
            
            # TEKNOSA
            'TEKNOSA_API_KEY': re.compile(r'\btkn_[0-9a-zA-Z]{28}\b'),
            
            # MEDIAMARKT
            'MEDIAMARKT_API_KEY': re.compile(r'\bmm_[0-9a-f]{30}\b'),
            
            # VESTEL
            'VESTEL_API_KEY': re.compile(r'\bvst_[0-9a-zA-Z]{26}\b'),
            
            # ARCELIK
            'ARCELIK_API_KEY': re.compile(r'\barc_[0-9a-f]{32}\b'),
            
            # BOSCH
            'BOSCH_API_KEY': re.compile(r'\bbos_[0-9a-zA-Z]{28}\b'),
            
            # SIEMENS
            'SIEMENS_API_KEY': re.compile(r'\bsie_[0-9a-f]{30}\b'),
            
            # GENERAL ELECTRIC
            'GE_API_KEY': re.compile(r'\bge_[0-9a-zA-Z]{26}\b'),
            
            # TÜRK HAVA YOLLARI
            'THY_API_KEY': re.compile(r'\bthy_[0-9a-f]{36}\b'),
            
            # PEGASUS
            'PEGASUS_API_KEY': re.compile(r'\bpg_[0-9a-zA-Z]{32}\b'),
            
            # ANADOLUJET
            'ANADOLUJET_API_KEY': re.compile(r'\baj_[0-9a-f]{30}\b'),
            
            # SUNEXPRESS
            'SUNEXPRESS_API_KEY': re.compile(r'\bsun_[0-9a-zA-Z]{28}\b'),
            
            # ONUR AIR
            'ONURAIR_API_KEY': re.compile(r'\boa_[0-9a-f]{26}\b'),
            
            # ATLASJET
            'ATLASJET_API_KEY': re.compile(r'\batl_[0-9a-zA-Z]{24}\b'),
            
            # TURKISH CARGO
            'TURKISH_CARGO_API_KEY': re.compile(r'\btcgo_[0-9a-f]{34}\b'),
            
            # MNG KARGO
            'MNG_API_KEY': re.compile(r'\bmng_[0-9a-zA-Z]{32}\b'),
            
            # YURTİÇİ KARGO
            'YURTICI_API_KEY': re.compile(r'\byk_[0-9a-f]{30}\b'),
            
            # ARAS KARGO
            'ARAS_API_KEY': re.compile(r'\baras_[0-9a-zA-Z]{28}\b'),
            
            # SURAT KARGO
            'SURAT_API_KEY': re.compile(r'\bsrt_[0-9a-f]{26}\b'),
            
            # PTT KARGO
            'PTT_API_KEY': re.compile(r'\bptt_[0-9a-zA-Z]{24}\b'),
            
            # DHL
            'DHL_API_KEY': re.compile(r'\bdhl_[0-9a-f]{32}\b'),
            
            # UPS
            'UPS_API_KEY': re.compile(r'\bups_[0-9a-zA-Z]{30}\b'),
            
            # FEDEX
            'FEDEX_API_KEY': re.compile(r'\bfdx_[0-9a-f]{28}\b'),
            
            # TNT
            'TNT_API_KEY': re.compile(r'\btnt_[0-9a-zA-Z]{26}\b'),
        }

        # Taban domain'i RegeX escape et
        escaped_taban_domain = re.escape(self.taban_domain)

        self.paternler = {
            'api_endpoint': re.compile(r'(?:api|endpoint|route)[\"\']?\s*[:=]\s*[\"\']([^\"\']+)[\"\']', re.IGNORECASE),
            'url_paterni': re.compile(r'(https?://[^\s<>\"\'{}|\\^`\[\]]+)', re.IGNORECASE),
            'goreceli_url': re.compile(r'[\"\'](/[a-zA-Z0-9_\-/.?&=]+)[\"\']'),
            'eposta': re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'),
            'alt_domain': re.compile(r'https?://([a-zA-Z0-9.-]+\.' + escaped_taban_domain + r')'),
            'fetch_cagrisi': re.compile(r'fetch\s*\(\s*[\"\']([^\"\']+)[\"\']'),
            'axios_cagrisi': re.compile(r'axios\.\w+\s*\(\s*[\"\']([^\"\']+)[\"\']'),
            'ajax_cagrisi': re.compile(r'\$\.(?:ajax|get|post)\s*\(\s*[\"\']([^\"\']+)[\"\']'),
            'websocket': re.compile(r'new\s+WebSocket\s*\(\s*[\"\']([^\"\']+)[\"\']'),
            'graphql': re.compile(r'(?:graphql|gql)`([^`]+)`'),
            'js_url': re.compile(r'[\"\'](https?://[^\"\']+)[\"\']', re.IGNORECASE),
            'js_yol': re.compile(r'(?:path|url|endpoint|api|href|src)\s*[:=]\s*[\"\'](https?://[^\"\']+)[\"\']', re.IGNORECASE),
            'js_sablon': re.compile(r'`(https?://[^`]+)`', re.IGNORECASE),
            'js_string_url': re.compile(r'[\"\'](https?://[a-zA-Z0-9\-._~:/?#\[\]@!$&\'()*+,;=]+)[\"\']'),
            'meta_url': re.compile(r'<meta[^>]+(content|url)=["\']([^"\']+)["\']', re.IGNORECASE),
            'data_url': re.compile(r'data-[\w-]+=["\']([^"\']+)["\']'),
        }

        # False positive filtreleme için pattern'ler
        self.false_positive_patterns = [
            re.compile(r'^[0-9]+$'),  # Sadece sayılar
            re.compile(r'^[a-f0-9]{32}$'),  # MD5 hash'leri
            re.compile(r'^https?://'),  # URL'ler
            re.compile(r'^data:'),  # Data URL'leri
            re.compile(r'^[A-Z]{2}[0-9]{3,}$'),  # Posta kodları vb.
            re.compile(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$'),  # IP adresleri
            re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'),  # E-posta adresleri
            re.compile(r'\.(com|net|org|io|gov|edu)$'),  # Domain sonları
            re.compile(r'^/'),  # Yol başlangıçları
            re.compile(r'^[A-Z]{3}$'),  # 3 harfli kısaltmalar
        ]

        # Çıktı dosyalarını başlat
        if self.cikti_dosyasi:
            with open(self.cikti_dosyasi, 'a', encoding='utf-8') as f:
                f.write(f"# Web Tarayıcı Sonuçları - {self.hedef_url}\n")
                f.write(f"# Başlangıç zamanı: {datetime.now().isoformat()}\n")
                f.write("# Format: TAM_URL\n")
                f.write("# =====================\n\n")

        if self.eposta_dosyasi:
            with open(self.eposta_dosyasi, 'a', encoding='utf-8') as f:
                f.write(f"# Bulunan E-posta Adresleri - {self.hedef_url}\n")
                f.write(f"# Başlangıç zamanı: {datetime.now().isoformat()}\n")
                f.write("# =====================\n\n")

        if self.api_key_bul and self.api_anahtari_dosyasi:
            with open(self.api_anahtari_dosyasi, 'a', encoding='utf-8') as f:
                f.write(f"# Bulunan API Anahtarları - {self.hedef_url}\n")
                f.write(f"# Başlangıç zamanı: {datetime.now().isoformat()}\n")
                f.write("# =====================\n\n")

        if self.api_key_bul:
            with open(self.kritik_dosyasi, 'a', encoding='utf-8') as f:
                f.write(f"# KRİTİK BULGULAR - {self.hedef_url}\n")
                f.write(f"# Başlangıç zamanı: {datetime.now().isoformat()}\n")
                f.write("# =====================\n\n")

        if self.param_dosyasi:
            with open(self.param_dosyasi, 'a', encoding='utf-8') as f:
                f.write(f"# Benzersiz Parametreler - {self.hedef_url}\n")
                f.write(f"# Başlangıç zamanı: {datetime.now().isoformat()}\n")
                f.write("# Format: /path/to/endpoint\n")
                f.write("# =====================\n\n")

    def tor_baglanti_testi(self) -> bool:
        """TOR bağlantısını test et"""
        try:
            test_url = "https://check.torproject.org"
            response = self.oturum.get(test_url, timeout=15, verify=not self.disable_ssl)
            return "Congratulations" in response.text
        except:
            return False

    def basliklari_guncelle(self, ozel_kullanici_araci: str = None):
        if ozel_kullanici_araci:
            kullanici_araci = ozel_kullanici_araci
        elif self.taklit_modu:
            kullanici_araci = random.choice(self.kullanici_araclari)
        else:
            kullanici_araci = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'

        basliklar = {
            'User-Agent': kullanici_araci,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Cache-Control': 'max-age=0',
        }

        if self.taklit_modu:
            basliklar.update({
                'Accept-Language': random.choice(self.kabul_dilleri),
                'Accept-Encoding': random.choice(self.kabul_sifrelemeleri),
                'Cache-Control': random.choice(['max-age=0', 'no-cache', '']),
            })

        self.oturum.headers.update(basliklar)

    def param_dosyasina_kaydet(self, parametre: str):
        if not self.param_dosyasi:
            return

        try:
            with self.kilit:
                if parametre not in self.benzersiz_parametreler:
                    self.benzersiz_parametreler.add(parametre)
                    with open(self.param_dosyasi, 'a', encoding='utf-8') as f:
                        f.write(f"{parametre}\n")
        except Exception as e:
            print(f"{Fore.RED}[-] Parametre dosyasına kaydetme hatası: {str(e)}{Style.RESET_ALL}")

    def parmakizi_degistir(self):
        if self.taklit_modu and self.istek_sayisi - self.son_taklit_degisimi >= 50:
            self.basliklari_guncelle()
            self.son_taklit_degisimi = self.istek_sayisi
            if random.random() < 0.3:
                # Yeni session oluştur
                self.oturum = requests.Session()
                if self.disable_ssl:
                    self.oturum.verify = False
                if self.tor_kullan:
                    tor_proxy = {
                        'http': 'socks5h://127.0.0.1:9050',
                        'https': 'socks5h://127.0.0.1:9050'
                    }
                    self.oturum.proxies = tor_proxy
                self.basliklari_guncelle()
            return True
        return False

    def uzantiyi_atla(self, url: str) -> bool:
        if not self.resim_dosyalari_atla:
            return False

        parsed = urlparse(url)
        yol = parsed.path.lower()

        for uzanti in self.atlanacak_uzantilar:
            if yol.endswith(uzanti):
                return True

        return False

    def url_normalize_et(self, url: str) -> str:
        """URL'yi normalize et"""
        try:
            parsed = urlparse(url)
            sema = parsed.scheme.lower() if parsed.scheme else 'https'
            ag_konumu = parsed.netloc.lower()
            yol = parsed.path.rstrip('/')
            if not yol:
                yol = '/'

            sorgu = ''
            if parsed.query:
                params = parse_qs(parsed.query, keep_blank_values=True)
                sorted_params = sorted(params.items())
                sorgu = urlencode(sorted_params, doseq=True)

            if sorgu:
                normalize_edilmis = f"{sema}://{ag_konumu}{yol}?{sorgu}"
            else:
                normalize_edilmis = f"{sema}://{ag_konumu}{yol}"

            return normalize_edilmis
        except:
            return url.lower().rstrip('/')

    def url_benzersiz_mi(self, url: str) -> bool:
        normalize_edilmis = self.url_normalize_et(url)
        return normalize_edilmis not in self.benzersiz_url_yollari

    def url_goruldu_olarak_isaretle(self, url: str):
        """URL'yi hem benzersiz yollara hem de ziyaret edilenlere ekle"""
        normalize_edilmis = self.url_normalize_et(url)
        if len(self.benzersiz_url_yollari) < self.MAX_URL:
            self.benzersiz_url_yollari.add(normalize_edilmis)

        self.ziyaret_edilen_url.add(normalize_edilmis)

    def google_url_mi(self, url: str) -> bool:
        if not self.google_servisleri_gormezden_gel:
            return False

        # Google Drive ve Docs gibi servisleri atlama
        for pattern in self.google_servis_patternleri:
            if re.search(pattern, url, re.IGNORECASE):
                return True

        # Diğer Google servisleri
        for pattern in self.google_paternleri:
            if re.search(pattern, url, re.IGNORECASE):
                return True
                
        return False

    def subfinder_calistir(self):
        print(f"\n{Fore.RED}::{Style.RESET_ALL}{Fore.LIGHTBLACK_EX} Subfinder çalıştırılıyor: {self.taban_domain}{Style.RESET_ALL}")

        try:
            komut = ["subfinder", "-d", self.taban_domain, "-silent"]
            sonuc = subprocess.run(komut, capture_output=True, text=True, timeout=300)

            if sonuc.returncode == 0:
                alt_domainler = sonuc.stdout.strip().split('\n')
                alt_domainler = [s.strip() for s in alt_domainler if s.strip()]

                print(f"{Fore.RED}::{Style.RESET_ALL}{Fore.LIGHTBLACK_EX} {len(alt_domainler)} alt domain bulundu{Style.RESET_ALL}")

                for alt_domain in alt_domainler:
                    url = f"https://{alt_domain}"
                    if self.url_gecerli_mi(url) and not self.google_url_mi(url) and not self.uzantiyi_atla(url):
                        if self.url_benzersiz_mi(url) and url not in self.ziyaret_edilen_url and url not in [u for u, d in self.ziyaret_edilecek]:
                            self.ziyaret_edilecek.append((url, 0))
                            self.benzersiz_oge_ekle('alt_domainler', '', alt_domain)
                return True
            else:
                print(f"{Fore.RED}[-] Subfinder başarısız: {sonuc.stderr}{Style.RESET_ALL}")
                return False
        except FileNotFoundError:
            print(f"{Fore.RED}[-] Subfinder bulunamadı. Lütfen yükleyin: https://github.com/projectdiscovery/subfinder{Style.RESET_ALL}")
            return False
        except subprocess.TimeoutExpired:
            print(f"{Fore.RED}[-] Subfinder zaman aşımı{Style.RESET_ALL}")
            return False
        except Exception as e:
            print(f"{Fore.RED}[-] Subfinder hatası: {str(e)}{Style.RESET_ALL}")
            return False

    def bellek_kullanimi(self):
        proses = psutil.Process(os.getpid())
        return proses.memory_info().rss / 1024 / 1024

    def banner_yazdir(self, chain_mode=False, chain_index=None, total_chains=None):
        print(f"{Fore.CYAN}")
        yuklenme_animasyonu("Web Tarayıcı Başlatılıyor", sure=1.5)
        print(f"\r{Style.RESET_ALL}")

        banner = f"""
{Fore.LIGHTBLACK_EX}
       .__                 .__
  ____ |  |__   ___________|__|
_/ ___\\|  |  \\_/ __ \\_  __ \\  |                                                      
 \\  \\___|   Y  \\  ___/|  | \\/  |
 \\___  >___|  /\\___  >__|  |__|
     \\/     \\/     \\/
                         0.xxx : Code Owner 
{Style.RESET_ALL}                                                                        
{Fore.RED}::{Style.RESET_ALL}{Fore.LIGHTBLACK_EX} Method           : {self.method}{Style.RESET_ALL}
{Fore.RED}::{Style.RESET_ALL}{Fore.LIGHTBLACK_EX} URL              : {self.hedef_url}{Style.RESET_ALL}
{Fore.RED}::{Style.RESET_ALL}{Fore.LIGHTBLACK_EX} Timeout          : {self.zaman_asimi}s{Style.RESET_ALL}
{Fore.RED}::{Style.RESET_ALL}{Fore.LIGHTBLACK_EX} Threads          : {self.maksimum_thread}{Style.RESET_ALL}
{Fore.RED}::{Style.RESET_ALL}{Fore.LIGHTBLACK_EX} Max Depth        : {self.maksimum_derinlik}{Style.RESET_ALL}
{Fore.RED}::{Style.RESET_ALL}{Fore.LIGHTBLACK_EX} Delay            : {self.bekleme_suresi}s{Style.RESET_ALL}
{Fore.RED}::{Style.RESET_ALL}{Fore.LIGHTBLACK_EX} TOR Proxy        : {self.tor_kullan}{Style.RESET_ALL}
{Fore.RED}::{Style.RESET_ALL}{Fore.LIGHTBLACK_EX} Max Content Size : {"Sınırsız" if self.max_content_size == 0 else f"{self.max_content_size/1_000_000}MB"}{Style.RESET_ALL}
"""
        
        if chain_mode and chain_index is not None and total_chains is not None:
            banner += f"{Fore.RED}::{Style.RESET_ALL}{Fore.LIGHTBLACK_EX} Chain Modu       : {chain_index + 1}/{total_chains}{Style.RESET_ALL}"
        
        print(banner)

    def benzersiz_oge_ekle(self, kategori: str, alt_kategori: str, oge: str):
        if alt_kategori:
            if oge not in self.sonuclar[kategori][alt_kategori]:
                self.sonuclar[kategori][alt_kategori].append(oge)
        else:
            if oge not in self.sonuclar[kategori]:
                self.sonuclar[kategori].append(oge)

    def benzersiz_eposta_ekle(self, eposta: str):
        if eposta and eposta not in self.sonuclar['eposta_adresleri']:
            self.sonuclar['eposta_adresleri'].append(eposta)
            if self.eposta_dosyasi:
                self.eposta_dosyasina_kaydet(eposta)

    def eposta_dosyasina_kaydet(self, eposta: str):
        try:
            with self.kilit:
                with open(self.eposta_dosyasi, 'a', encoding='utf-8') as f:
                    f.write(f"{eposta}\n")
        except Exception as e:
            print(f"{Fore.RED}[-] E-posta dosyasına kaydetme hatası: {str(e)}{Style.RESET_ALL}")

    def tum_epostalari_dosyaya_kaydet(self):
        if self.eposta_dosyasi and self.sonuclar['eposta_adresleri']:
            try:
                with self.kilit:
                    with open(self.eposta_dosyasi, 'a', encoding='utf-8') as f:
                        f.write(f"\n# Toplam benzersiz e-posta bulundu: {len(set(self.sonuclar['eposta_adresleri']))}\n")
                        f.write(f"# Tarama tamamlanma zamanı: {datetime.now().isoformat()}\n")
            except Exception as e:
                print(f"{Fore.RED}[-] E-posta sayısını kaydetme hatası: {str(e)}{Style.RESET_ALL}")

    def api_anahtari_dosyaya_kaydet(self, anahtar_turu: str, anahtar_degeri: str, url: str, icerik: str = ""):
        if not self.api_key_bul or not self.api_anahtari_dosyasi:
            return

        try:
            with self.kilit:
                with open(self.api_anahtari_dosyasi, 'a', encoding='utf-8') as f:
                    f.write(f"URL: {url}\n")
                    f.write(f"Tür: {anahtar_turu}\n")
                    f.write(f"Değer: {anahtar_degeri}\n")
                    if icerik:
                        f.write(f"İçerik: {icerik[:200]}...\n")
                    f.write("# ---\n\n")
        except Exception as e:
            print(f"{Fore.RED}[-] API anahtarı dosyasına kaydetme hatası: {str(e)}{Style.RESET_ALL}")

    def kritik_dosyaya_kaydet(self, tur: str, deger: str, url: str):
        if not self.api_key_bul:
            return

        try:
            with self.kilit:
                with open(self.kritik_dosyasi, 'a', encoding='utf-8') as f:
                    if tur == "API_ANAHTARI":
                        f.write(f"[KRİTİK] API anahtarı : {deger} <= {url}\n\n")
        except Exception as e:
            print(f"{Fore.RED}[-] Kritik dosyasına kaydetme hatası: {str(e)}{Style.RESET_ALL}")

    def ozel_filtre_uyuyor_mu(self, url: str) -> bool:
        if not self.ozel_filtre:
            return True
        return self.ozel_filtre.lower() in url.lower()

    def cikti_dosyasina_kaydet(self, url: str):
        if not self.cikti_dosyasi or not self.ozel_filtre_uyuyor_mu(url):
            return

        if not self.url_benzersiz_mi(url):
            return

        try:
            with self.kilit:
                self.url_goruldu_olarak_isaretle(url)
                with open(self.cikti_dosyasi, 'a', encoding='utf-8') as f:
                    f.write(f"{url}\n")

                parsed = urlparse(url)
                if parsed.path and parsed.path != '/':
                    self.param_dosyasina_kaydet(parsed.path)
        except Exception as e:
            print(f"{Fore.RED}[-] Çıktı dosyasına kaydetme hatası: {str(e)}{Style.RESET_ALL}")

    def epostalari_cikti_dosyasina_kaydet(self):
        if self.cikti_dosyasi and self.sonuclar['eposta_adresleri']:
            try:
                with self.kilit:
                    with open(self.cikti_dosyasi, 'a', encoding='utf-8') as f:
                        f.write("\n# =====================\n")
                        f.write("# BULUNAN E-POSTA ADRESLERİ\n")
                        f.write("# =====================\n")
                        for eposta in sorted(set(self.sonuclar['eposta_adresleri'])):
                            f.write(f"{eposta}\n")
                        f.write(f"\n# Toplam benzersiz e-posta bulundu: {len(set(self.sonuclar['eposta_adresleri']))}\n")
            except Exception as e:
                print(f"{Fore.RED}[-] E-postaları çıktı dosyasına kaydetme hatası: {str(e)}{Style.RESET_ALL}")

    def url_gecerli_mi(self, url: str) -> bool:
        try:
            sonuc = urlparse(url)
            if self.sadece_https and sonuc.scheme != 'https':
                return False
            return all([sonuc.scheme, sonuc.netloc])
        except:
            return False

    def ayni_domain_mi(self, url: str) -> bool:
        parsed = urlparse(url)
        netloc = parsed.netloc.lower()
        return netloc.endswith(self.taban_domain)

    def url_islenmeli_mi(self, url: str) -> bool:
        if not self.ozel_filtre:
            return True
        return self.ozel_filtre_uyuyor_mu(url)

    def url_getir(self, url: str, method: str = 'GET') -> tuple:
        try:
            with self.kilit:
                self.istek_sayisi += 1

            self.parmakizi_degistir()

            with self.sema:
                verify_ssl = not self.disable_ssl

                if method == 'POST':
                    yanit = self.oturum.post(url, timeout=self.zaman_asimi, allow_redirects=True, stream=True, verify=verify_ssl)
                elif method == 'PUT':
                    yanit = self.oturum.put(url, timeout=self.zaman_asimi, allow_redirects=True, stream=True, verify=verify_ssl)
                elif method == 'DELETE':
                    yanit = self.oturum.delete(url, timeout=self.zaman_asimi, allow_redirects=True, stream=True, verify=verify_ssl)
                elif method == 'PATCH':
                    yanit = self.oturum.patch(url, timeout=self.zaman_asimi, allow_redirects=True, stream=True, verify=verify_ssl)
                elif method == 'HEAD':
                    yanit = self.oturum.head(url, timeout=self.zaman_asimi, allow_redirects=True, stream=True, verify=verify_ssl)
                elif method == 'OPTIONS':
                    yanit = self.oturum.options(url, timeout=self.zaman_asimi, allow_redirects=True, stream=True, verify=verify_ssl)
                else:
                    yanit = self.oturum.get(url, timeout=self.zaman_asimi, allow_redirects=True, stream=True, verify=verify_ssl)

                # İçerik boyutu kontrolü - sadece max_content_size > 0 ise kontrol et
                if self.max_content_size > 0:
                    content_length = yanit.headers.get("Content-Length")
                    if content_length:
                        try:
                            if int(content_length) > self.max_content_size:
                                print(f"{Fore.YELLOW}[!] İçerik çok büyük ({int(content_length)/1_000_000:.1f}MB), atlanıyor: {url}{Style.RESET_ALL}")
                                return None, None, None
                        except:
                            pass

                # İçeriği sınırlı oku - sadece max_content_size > 0 ise sınırla
                if self.max_content_size > 0:
                    max_read_size = min(self.max_content_size, 5_000_000)  # Max 5MB oku
                else:
                    max_read_size = None  # Sınırsız

                text = ""
                try:
                    # Stream olarak oku
                    content_bytes = b""
                    for chunk in yanit.iter_content(chunk_size=8192):
                        content_bytes += chunk
                        if max_read_size and len(content_bytes) > max_read_size:
                            print(f"{Fore.YELLOW}[!] İçerik sınırı aşıldı, kısmi okuma: {url}{Style.RESET_ALL}")
                            break
                    
                    # Encoding tespiti
                    try:
                        text = content_bytes.decode('utf-8')
                    except:
                        try:
                            text = content_bytes.decode('latin-1')
                        except:
                            text = content_bytes.decode('utf-8', errors='ignore')
                            
                except Exception as e:
                    print(f"{Fore.YELLOW}[!] İçerik okuma hatası: {url} - {str(e)[:100]}{Style.RESET_ALL}")
                    return None, None, None

                icerik_turu = yanit.headers.get('Content-Type', '').lower()
                return text, icerik_turu, yanit.status_code

        except requests.exceptions.TooManyRedirects:
            print(f"{Fore.YELLOW}[!] Çok fazla yönlendirme: {url}{Style.RESET_ALL}")
            return None, None, None
        except requests.exceptions.SSLError as e:
            if not self.disable_ssl:
                print(f"{Fore.YELLOW}[!] SSL hatası: {url} - {str(e)[:100]}{Style.RESET_ALL}")
            return None, None, None
        except requests.exceptions.ConnectionError:
            return None, None, None
        except requests.exceptions.Timeout:
            print(f"{Fore.YELLOW}[!] Zaman aşımı: {url}{Style.RESET_ALL}")
            return None, None, None
        except Exception as e:
            with self.kilit:
                self.hata_sayisi += 1
            if self.hata_sayisi % 20 == 0:
                print(f"{Fore.YELLOW}[!] Toplam hata sayısı: {self.hata_sayisi}{Style.RESET_ALL}")
            return None, None, None

    def metinden_epostalari_cikar(self, metin: str, kaynak_url: str = ""):
        if not metin:
            return

        bulunan_epostalar = self.paternler['eposta'].findall(metin)
        for eposta in bulunan_epostalar:
            if len(eposta) > 5 and '@' in eposta and '.' in eposta.split('@')[-1]:
                self.benzersiz_eposta_ekle(eposta)

    def yuksek_entropi_mi(self, s: str) -> bool:
        """String'in entropisini hesapla (rasgelelik ölçüsü)"""
        if len(s) < 20:
            return False

        # Karakter çeşitliliği
        char_counts = {}
        for char in s:
            char_counts[char] = char_counts.get(char, 0) + 1

        # Entropi hesapla
        entropy = 0
        for count in char_counts.values():
            p = count / len(s)
            entropy -= p * log2(p)

        # Yüksek entropi (> 4.5) genellikle rasgele token'ları gösterir
        return entropy > 4.5

    def gercek_api_anahtari_mi(self, anahtar_degeri: str) -> bool:
        """API anahtarının gerçek olup olmadığını kontrol et - GELİŞMİŞ FİLTRELEME"""
        # Minimum uzunluk kontrolü
        if len(anahtar_degeri) < 16:
            return False

        # False positive pattern'leri ile kontrol
        for pattern in self.false_positive_patterns:
            if pattern.search(anahtar_degeri):
                return False

        # Çok yaygın false positive'ları filtrele
        if anahtar_degeri.lower() in ['test', 'demo', 'example', 'sample', 'dummy', 'fake']:
            return False
            
        # UUID kontrolü (UUID'ler genellikle API key değildir)
        uuid_pattern = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.IGNORECASE)
        if uuid_pattern.match(anahtar_degeri):
            return False
            
        # Base64 encoded data kontrolü (genellikle API key değildir)
        if anahtar_degeri.endswith('=') or ('+' in anahtar_degeri and '/' in anahtar_degeri):
            try:
                # Base64 decode denenebilir
                import base64
                decoded = base64.b64decode(anahtar_degeri + '===')
                if len(decoded) > 100:  # Büyük base64 veriler genellikle API key değildir
                    return False
            except:
                pass

        # Entropi kontrolü - rasgele görünen string'ler
        if self.yuksek_entropi_mi(anahtar_degeri):
            # Entropi yüksekse, bilinen API key pattern'lerinden biriyle eşleşmeli
            known_api_patterns = [
                r'^AKIA[0-9A-Z]{16}$',  # AWS
                r'^AIza[0-9A-Za-z\-_]{35}$',  # Google
                r'^sk_(live|test)_[0-9a-zA-Z]{24}$',  # Stripe
                r'^gh[oprstu]_[A-Za-z0-9_]{36}$',  # GitHub
                r'^xox[baprs]-[0-9]{12}-[0-9]{12}-[0-9a-zA-Z]{32}$',  # Slack
                r'^SG\.[0-9a-zA-Z\-_]{22}\.[0-9a-zA-Z\-_]{43}$',  # SendGrid
                r'^sk-[0-9a-zA-Z]{48}$',  # OpenAI
            ]
            
            for pattern in known_api_patterns:
                if re.match(pattern, anahtar_degeri):
                    return True
                    
            # Diğer pattern'ler için entropi threshold'unu yükselt
            return self.yuksek_entropi_mi(anahtar_degeri) and entropy > 5.0

        return True

    def api_anahtari_kontrol(self, icerik: str, url: str):
        if not self.api_key_bul:
            return

        for anahtar_turu, patern in self.api_key_patterns.items():
            for eslesme in patern.finditer(icerik):
                anahtar_degeri = eslesme.group(0)
                
                # False positive filtreleme
                if not self.gercek_api_anahtari_mi(anahtar_degeri):
                    continue
                    
                # URL'deki anahtarları filtrele (genellikle yanlış pozitiftir)
                if url and anahtar_degeri in url:
                    continue
                    
                # Aynı anahtarı birden fazla kez gösterme
                with self.kilit:
                    if any(api['anahtar'] == anahtar_degeri for api in self.bulunan_api_anahtarlari):
                        continue

                print(f"\n{Fore.RED}[KRİTİK] API anahtarı bulundu: {anahtar_turu} <= {url}{Style.RESET_ALL}")
                print(f"{Fore.YELLOW}Değer: {anahtar_degeri[:50]}...{Style.RESET_ALL}")

                baslangic = max(0, eslesme.start() - 50)
                bitis = min(len(icerik), eslesme.end() + 50)
                icerik_parcasi = icerik[baslangic:bitis].replace('\n', ' ').replace('\r', ' ')

                self.api_anahtari_dosyaya_kaydet(anahtar_turu, anahtar_degeri, url, icerik_parcasi)
                self.kritik_dosyaya_kaydet("API_ANAHTARI", anahtar_degeri, url)

                with self.kilit:
                    self.bulunan_api_anahtarlari.append({
                        'tur': anahtar_turu,
                        'anahtar': anahtar_degeri,
                        'url': url,
                        'icerik': icerik_parcasi[:200]
                    })

    def xml_icerigi_analiz(self, icerik: str, url: str):
        try:
            self.metinden_epostalari_cikar(icerik, url)
            if self.api_key_bul:
                self.api_anahtari_kontrol(icerik, url)

            icerik_temiz = re.sub(r'^<\?xml[^?>]*\?>', '', icerik.strip())
            kok = ET.fromstring(icerik_temiz)

            def xml_gez(element, yol=""):
                if element.text:
                    metin = element.text.strip()
                    if metin:
                        for eslesme in self.paternler['url_paterni'].finditer(metin):
                            bulunan_url = eslesme.group(0)
                            if self.url_gecerli_mi(bulunan_url) and self.url_islenmeli_mi(bulunan_url):
                                if self.google_url_mi(bulunan_url) or self.uzantiyi_atla(bulunan_url):
                                    return
                                if self.sadece_hedef and not self.ayni_domain_mi(bulunan_url):
                                    continue
                                self.url_islem(bulunan_url, url, 0)

                for ozellik_adi, ozellik_degeri in element.attrib.items():
                    if ozellik_degeri and self.url_gecerli_mi(ozellik_degeri) and self.url_islenmeli_mi(ozellik_degeri):
                        if self.google_url_mi(ozellik_degeri) or self.uzantiyi_atla(ozellik_degeri):
                            continue
                        if self.sadece_hedef and not self.ayni_domain_mi(ozellik_degeri):
                            continue
                        self.url_islem(ozellik_degeri, url, 0)

                for cocuk in element:
                    xml_gez(cocuk, yol + "/" + cocuk.tag)

            xml_gez(kok)
            self.benzersiz_oge_ekle('xml_dosyalari', '', url)

        except Exception as e:
            for eslesme in self.paternler['url_paterni'].finditer(icerik):
                bulunan_url = eslesme.group(0)
                if self.url_gecerli_mi(bulunan_url) and self.url_islenmeli_mi(bulunan_url):
                    if self.google_url_mi(bulunan_url) or self.uzantiyi_atla(bulunan_url):
                        continue
                    if self.sadece_hedef and not self.ayni_domain_mi(bulunan_url):
                        continue
                    self.url_islem(bulunan_url, url, 0)

    def url_islem(self, url: str, kaynak_url: str, mevcut_derinlik: int):
        """URL'yi işle ve gerekli kontrolleri yap"""
        if not url:
            return

        # URL'yi normalize et
        if url.startswith('//'):
            url = 'https:' + url
        elif url.startswith('/'):
            url = urljoin(kaynak_url, url)
        elif not url.startswith(('http://', 'https://', 'mailto:', 'tel:', 'javascript:', '#')):
            url = urljoin(kaynak_url, url)

        # Fragment'i kaldır
        url = url.split('#')[0]

        if not self.url_gecerli_mi(url) or not self.url_islenmeli_mi(url):
            return

        if self.google_url_mi(url) or self.uzantiyi_atla(url):
            return

        if self.sadece_hedef and not self.ayni_domain_mi(url):
            return

        if not self.url_benzersiz_mi(url):
            return

        parsed = urlparse(url)
        domain = parsed.netloc

        with self.kilit:
            if domain not in self.ziyaret_edilen_domainler:
                self.ziyaret_edilen_domainler.add(domain)

        if self.ayni_domain_mi(url):
            self.benzersiz_oge_ekle('linkler', 'iç', url)
            self.cikti_dosyasina_kaydet(url)

            with self.kilit:
                self.kesfedilen_url.add(url)

            if url not in self.ziyaret_edilen_url and url not in [u for u, d in self.ziyaret_edilecek]:
                self.ziyaret_edilecek.append((url, mevcut_derinlik + 1))
        else:
            self.benzersiz_oge_ekle('linkler', 'dış', url)
            self.cikti_dosyasina_kaydet(url)

    def linkleri_cikar(self, corba: BeautifulSoup, temel_url: str, mevcut_derinlik: int):
        """Tüm potansiyel URL'leri çıkar"""
        # Tüm tag'lerdeki URL attribute'larını kontrol et
        url_attributes = ['href', 'src', 'data-src', 'action', 'content', 'cite', 'data', 'poster', 'srcset']

        for etiket in corba.find_all(True):
            for attr in url_attributes:
                url = etiket.get(attr)
                if url:
                    self.url_islem(url, temel_url, mevcut_derinlik)

        # Meta tag'lerdeki URL'leri kontrol et
        for meta in corba.find_all('meta'):
            content = meta.get('content')
            if content and ('http://' in content or 'https://' in content):
                for eslesme in self.paternler['url_paterni'].finditer(content):
                    self.url_islem(eslesme.group(0), temel_url, mevcut_derinlik)

        # Script içeriklerindeki URL'leri kontrol et
        for script in corba.find_all('script'):
            if script.string:
                self.javascript_icerikten_url_cikar(script.string, temel_url, mevcut_derinlik)

    def javascript_icerikten_url_cikar(self, icerik: str, temel_url: str, mevcut_derinlik: int):
        """JavaScript içeriğinden URL'leri çıkar"""
        for eslesme in self.paternler['url_paterni'].finditer(icerik):
            self.url_islem(eslesme.group(0), temel_url, mevcut_derinlik)

        for eslesme in self.paternler['js_string_url'].finditer(icerik):
            self.url_islem(eslesme.group(0), temel_url, mevcut_derinlik)

        for eslesme in self.paternler['js_sablon'].finditer(icerik):
            self.url_islem(eslesme.group(0), temel_url, mevcut_derinlik)

    def formlari_cikar(self, corba: BeautifulSoup, temel_url: str):
        for form in corba.find_all('form'):
            action = form.get('action', '')
            method = form.get('method', 'GET').upper()

            if action:
                action_url = urljoin(temel_url, action)
            else:
                action_url = temel_url

            form_verisi = {
                'url': action_url,
                'method': method,
                'alanlar': []
            }

            for input_etiketi in form.find_all(['input', 'textarea', 'select']):
                alan = {
                    'tip': input_etiketi.get('type', 'text'),
                    'isim': input_etiketi.get('name', ''),
                    'deger': input_etiketi.get('value', '')
                }
                if alan['tip'] == 'hidden':
                    self.sonuclar['gizli_alanlar'].append({
                        'url': temel_url,
                        'isim': alan['isim'],
                        'deger': alan['deger']
                    })
                form_verisi['alanlar'].append(alan)

            self.sonuclar['formlar'].append(form_verisi)

    def yorumlari_cikar(self, corba: BeautifulSoup, temel_url: str):
        from bs4 import Comment

        yorumlar = corba.find_all(string=lambda text: isinstance(text, Comment))
        for yorum in yorumlar:
            yorum_metni = yorum.strip()
            if len(yorum_metni) > 10:
                self.sonuclar['yorumlar'].append({
                    'url': temel_url,
                    'icerik': yorum_metni
                })
                self.metinden_epostalari_cikar(yorum_metni, temel_url)
                if self.api_key_bul:
                    self.api_anahtari_kontrol(yorum_metni, temel_url)

    def js_url_cikar(self, icerik: str, url: str):
        bulunan_url = set()

        for eslesme in self.paternler['js_url'].finditer(icerik):
            bulunan_url.add(eslesme.group(1))

        for eslesme in self.paternler['js_yol'].finditer(icerik):
            bulunan_url.add(eslesme.group(1))

        for eslesme in self.paternler['js_sablon'].finditer(icerik):
            bulunan_url.add(eslesme.group(1))

        for eslesme in self.paternler['js_string_url'].finditer(icerik):
            bulunan_url.add(eslesme.group(1))

        for bulunan in bulunan_url:
            self.url_islem(bulunan, url, 0)

        return bulunan_url

    def endpoint_cikar(self, icerik: str, url: str):
        endpointler = set()

        for eslesme in self.paternler['goreceli_url'].finditer(icerik):
            endpoint = eslesme.group(1)
            if not endpoint.endswith(('.css', '.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.woff', '.woff2', '.ttf', '.eot')):
                endpointler.add(endpoint)

        for endpoint in endpointler:
            with self.kilit:
                if endpoint not in self.kesfedilen_endpointler:
                    self.kesfedilen_endpointler.add(endpoint)
                    js_endpoint_bilgi = {
                        'kaynak': url,
                        'endpoint': endpoint,
                        'tam_url': urljoin(self.hedef_url, endpoint) if endpoint.startswith('/') else endpoint
                    }
                    self.sonuclar['js_endpointleri'].append(js_endpoint_bilgi)

        return endpointler

    def javascript_analiz(self, icerik: str, url: str):
        self.metinden_epostalari_cikar(icerik, url)
        if self.api_key_bul:
            self.api_anahtari_kontrol(icerik, url)
        bulunan_url = self.js_url_cikar(icerik, url)
        endpointler = self.endpoint_cikar(icerik, url)

        with self.kilit:
            for endpoint in endpointler:
                if endpoint.startswith('/'):
                    self.kesfedilen_endpointler.add(endpoint)

        for eslesme in self.paternler['fetch_cagrisi'].finditer(icerik):
            endpoint = eslesme.group(1)
            tam_url = urljoin(url, endpoint) if not endpoint.startswith('http') else endpoint
            self.url_islem(tam_url, url, 0)

        for eslesme in self.paternler['axios_cagrisi'].finditer(icerik):
            endpoint = eslesme.group(1)
            tam_url = urljoin(url, endpoint) if not endpoint.startswith('http') else endpoint
            self.url_islem(tam_url, url, 0)

        for eslesme in self.paternler['ajax_cagrisi'].finditer(icerik):
            endpoint = eslesme.group(1)
            tam_url = urljoin(url, endpoint) if not endpoint.startswith('http') else endpoint
            self.url_islem(tam_url, url, 0)

        for eslesme in self.paternler['api_endpoint'].finditer(icerik):
            endpoint = eslesme.group(1)
            if endpoint.startswith('/'):
                tam_url = urljoin(self.hedef_url, endpoint)
                self.url_islem(tam_url, url, 0)

        for eslesme in self.paternler['websocket'].finditer(icerik):
            ws_url = eslesme.group(1)
            self.url_islem(ws_url, url, 0)

        for eslesme in self.paternler['graphql'].finditer(icerik):
            self.benzersiz_oge_ekle('api_endpointleri', '', 'GraphQL: ' + eslesme.group(1)[:100])

        for eslesme in self.paternler['goreceli_url'].finditer(icerik):
            yol = eslesme.group(1)
            if yol.startswith('/'):
                tam_url = urljoin(self.hedef_url, yol)
                if any(uzanti in yol for uzanti in ['.json', '.xml', '.txt', '.log', '.bak', '.config']):
                    self.url_islem(tam_url, url, 0)

        for eslesme in self.paternler['eposta'].finditer(icerik):
            self.benzersiz_eposta_ekle(eslesme.group(0))

        for eslesme in self.paternler['alt_domain'].finditer(icerik):
            alt_domain = eslesme.group(1)
            if alt_domain != self.domain:
                tam_url = f"https://{alt_domain}"
                if self.url_islenmeli_mi(tam_url) and not self.google_url_mi(tam_url) and not self.uzantiyi_atla(tam_url):
                    if self.sadece_hedef and not self.ayni_domain_mi(tam_url):
                        continue
                    self.benzersiz_oge_ekle('alt_domainler', '', alt_domain)
                    self.cikti_dosyasina_kaydet(tam_url)

    def endpoint_test(self):
        if not self.endpoint_testi or not self.kesfedilen_endpointler:
            return

        if not self.gorevlendirici:
            print(f"\n{Fore.YELLOW}[!] Görevlendirici modu kapalı, endpoint testi atlanıyor{Style.RESET_ALL}")
            return

        print(f"\n{Fore.RED}::{Style.RESET_ALL}{Fore.LIGHTBLACK_EX} {len(self.kesfedilen_endpointler)} endpoint {len(self.kesfedilen_url)} URL üzerinde test ediliyor...{Style.RESET_ALL}")

        test_kombinasyonlari = []
        for endpoint in self.kesfedilen_endpointler:
            for url in self.kesfedilen_url:
                parsed = urlparse(url)
                temel_url = f"{parsed.scheme}://{parsed.netloc}"
                if endpoint.startswith('/'):
                    test_url = temel_url + endpoint
                    if self.google_url_mi(test_url) or self.uzantiyi_atla(test_url):
                        continue
                    if not self.url_benzersiz_mi(test_url):
                        continue
                    test_kombinasyonlari.append((test_url, endpoint, url))

        print(f"{Fore.RED}::{Style.RESET_ALL}{Fore.LIGHTBLACK_EX} {len(test_kombinasyonlari)} kombinasyon test ediliyor...{Style.RESET_ALL}")

        if self.method == 'ALL':
            methodlar = ['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS']
        else:
            methodlar = [self.method]

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.maksimum_thread) as yonetici:
            gorevler = []

            for test_url, endpoint, kaynak_url in test_kombinasyonlari:
                if test_url not in self.ziyaret_edilen_url and test_url not in [u for u, d in self.ziyaret_edilecek]:
                    for method in methodlar:
                        gorev = yonetici.submit(self.tek_endpoint_test, test_url, endpoint, kaynak_url, method)
                        gorevler.append(gorev)

            for gorev in concurrent.futures.as_completed(gorevler):
                try:
                    sonuc = gorev.result()
                    if sonuc:
                        test_url, endpoint, kaynak_url, durum_kodu, kullanilan_method = sonuc
                        if durum_kodu in [200, 201, 202, 204, 301, 302, 307, 308, 401, 403, 500]:
                            self.cikti_dosyasina_kaydet(test_url)
                            with self.kilit:
                                if test_url not in self.kesfedilen_url:
                                    self.kesfedilen_url.add(test_url)
                except Exception as e:
                    pass

        print(f"{Fore.RED}::{Style.RESET_ALL}{Fore.LIGHTBLACK_EX} Endpoint testi tamamlandı!{Style.RESET_ALL}")

    def tek_endpoint_test(self, test_url: str, endpoint: str, kaynak_url: str, method: str = 'GET'):
        try:
            with self.kilit:
                self.istek_sayisi += 1

            self.parmakizi_degistir()

            with self.sema:
                verify_ssl = not self.disable_ssl

                if method == 'POST':
                    yanit = self.oturum.post(test_url, timeout=self.zaman_asimi, allow_redirects=False, stream=True, verify=verify_ssl)
                elif method == 'PUT':
                    yanit = self.oturum.put(test_url, timeout=self.zaman_asimi, allow_redirects=False, stream=True, verify=verify_ssl)
                elif method == 'DELETE':
                    yanit = self.oturum.delete(test_url, timeout=self.zaman_asimi, allow_redirects=False, stream=True, verify=verify_ssl)
                elif method == 'PATCH':
                    yanit = self.oturum.patch(test_url, timeout=self.zaman_asimi, allow_redirects=False, stream=True, verify=verify_ssl)
                elif method == 'HEAD':
                    yanit = self.oturum.head(test_url, timeout=self.zaman_asimi, allow_redirects=False, stream=True, verify=verify_ssl)
                elif method == 'OPTIONS':
                    yanit = self.oturum.options(test_url, timeout=self.zaman_asimi, allow_redirects=False, stream=True, verify=verify_ssl)
                else:
                    yanit = self.oturum.get(test_url, timeout=self.zaman_asimi, allow_redirects=False, stream=True, verify=verify_ssl)

                content_length = yanit.headers.get("Content-Length")
                if content_length and int(content_length) > 500_000:
                    return None

                return test_url, endpoint, kaynak_url, yanit.status_code, method
        except:
            return None

    def url_tara(self, url: str, derinlik: int):
        if url in self.ziyaret_edilen_url or derinlik > self.maksimum_derinlik or not self.url_islenmeli_mi(url):
            return

        if len(self.ziyaret_edilen_url) >= self.MAX_URL:
            return

        with self.kilit:
            self.ziyaret_edilen_url.add(url)
            self.kesfedilen_url.add(url)

            parsed = urlparse(url)
            domain = parsed.netloc
            if domain not in self.ziyaret_edilen_domainler:
                self.ziyaret_edilen_domainler.add(domain)

        if self.method == 'ALL':
            methodlar = ['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS']
        else:
            methodlar = [self.method]

        icerik = None
        icerik_turu = None
        durum_kodu = None

        for method in methodlar:
            c, ct, sc = self.url_getir(url, method)
            if c and sc == 200:
                icerik = c
                icerik_turu = ct
                durum_kodu = sc
                break

        if not icerik or durum_kodu != 200:
            return

        self.metinden_epostalari_cikar(icerik, url)
        if self.api_key_bul:
            self.api_anahtari_kontrol(icerik, url)

        if 'xml' in icerik_turu or url.endswith(('.xml', '.rss', '.atom')):
            self.xml_icerigi_analiz(icerik, url)
            return

        if 'javascript' in icerik_turu or url.endswith('.js'):
            with self.kilit:
                self.benzersiz_oge_ekle('js_dosyalari', '', url)
            self.javascript_analiz(icerik, url)
            return

        if 'html' in icerik_turu:
            try:
                corba = BeautifulSoup(icerik, 'html.parser')

                self.linkleri_cikar(corba, url, derinlik)
                self.formlari_cikar(corba, url)
                self.yorumlari_cikar(corba, url)

                for script in corba.find_all('script'):
                    if script.string:
                        self.javascript_analiz(script.string, url)

                for script in corba.find_all('script', src=True):
                    js_url = urljoin(url, script['src'])
                    if self.url_gecerli_mi(js_url) and self.url_islenmeli_mi(js_url) and not self.google_url_mi(js_url) and not self.uzantiyi_atla(js_url):
                        if self.sadece_hedef and not self.ayni_domain_mi(js_url):
                            continue
                        with self.kilit:
                            self.benzersiz_oge_ekle('js_dosyalari', '', js_url)
                        if js_url not in self.ziyaret_edilen_url and self.ayni_domain_mi(js_url):
                            self.ziyaret_edilecek.append((js_url, derinlik + 1))

            except Exception as e:
                with self.kilit:
                    self.hata_sayisi += 1

        # Bekleme süresi - thread başına optimize edilmiş
        time.sleep(self.bekleme_suresi)

        if self.istek_sayisi % 500 == 0:
            gc.collect()

    def ilerlemeyi_guncelle(self):
        gecen_zaman = time.time() - self.baslangic_zamani
        dakikalar = int(gecen_zaman // 60)
        saniyeler = int(gecen_zaman % 60)
        zaman_string = f"{dakikalar:02d}.{saniyeler:02d}"
        
        taranan = len(self.ziyaret_edilen_url)
        kalan = len(self.ziyaret_edilecek)
        toplam = taranan + kalan
        bellek = self.bellek_kullanimi()

        if toplam > 0:
            print(f"\r{Fore.RED}::{Style.RESET_ALL}{Fore.LIGHTBLACK_EX} [URL : {taranan}] - [TIME : {zaman_string}] - [{toplam} URL Bulundu] - [{bellek:.1f}MB Ram Kullanımı]", end="")
        else:
            print(f"\r{Fore.RED}::{Style.RESET_ALL}{Fore.LIGHTBLACK_EX} [URL : {taranan}] - [TIME : {zaman_string}] - [Başlatılıyor...] - [{bellek:.1f}MB Ram Kullanımı]", end="")
        sys.stdout.flush()

    def zaman_guvenlik_modu_kontrol(self):
        if self.zaman_guvenlik_modu:
            taranan_sayisi = len(self.ziyaret_edilen_url)
            if taranan_sayisi - self.son_durdurma_sayisi >= 1000:
                print(f"\n{Fore.YELLOW}[!] Zaman Güvenlik Modu: 1000 link tarandı, 45 saniye duraklanıyor...{Style.RESET_ALL}")
                time.sleep(45)
                self.son_durdurma_sayisi = taranan_sayisi
                print(f"{Fore.GREEN}[+] Tarama devam ediyor...{Style.RESET_ALL}")

    def tara(self, chain_mode=False, chain_index=None, total_chains=None):
        self.banner_yazdir(chain_mode, chain_index, total_chains)

        if self.subfinder_kullan:
            if not self.subfinder_calistir():
                print(f"{Fore.RED}[-] Subfinder başarısız, alt domainler olmadan devam ediliyor{Style.RESET_ALL}")

        self.baslangic_zamani = time.time()
        self.ilerlemeyi_guncelle()

        son_guncelleme = time.time()
        guncelleme_araligi = 0.5
        empty_cycles = 0  # Boş döngü sayacı

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.maksimum_thread) as yonetici:
            gorevler = []

            while (self.ziyaret_edilecek or gorevler) and len(self.ziyaret_edilen_url) < self.MAX_URL:
                self.zaman_guvenlik_modu_kontrol()
                while self.ziyaret_edilecek and len(gorevler) < self.maksimum_thread:
                    url, derinlik = self.ziyaret_edilecek.popleft()
                    gorev = yonetici.submit(self.url_tara, url, derinlik)
                    gorevler.append(gorev)

                tamamlanan, tamamlanmayan = concurrent.futures.wait(gorevler, timeout=0.1, return_when=concurrent.futures.FIRST_COMPLETED)
                for gorev in tamamlanan:
                    try:
                        gorev.result()
                    except Exception as e:
                        with self.kilit:
                            self.hata_sayisi += 1
                    gorevler.remove(gorev)
                
                simdi = time.time()
                if simdi - son_guncelleme >= guncelleme_araligi:
                    self.ilerlemeyi_guncelle()
                    son_guncelleme = simdi
                
                # Boş döngü kontrolü
                if not self.ziyaret_edilecek and not gorevler:
                    empty_cycles += 1
                    if empty_cycles % 10 == 0:
                        print(f"[WAIT] {empty_cycles} cycles waiting...")
                    time.sleep(0.5)

        self.ilerlemeyi_guncelle()

        if self.endpoint_testi:
            self.endpoint_test()

        if self.cikti_dosyasi:
            self.epostalari_cikti_dosyasina_kaydet()

        if self.eposta_dosyasi:
            self.tum_epostalari_dosyaya_kaydet()

        print(f"\n\n{Fore.RED}::{Style.RESET_ALL}{Fore.LIGHTBLACK_EX} Tarama {time.time() - self.baslangic_zamani:.2f} saniyede tamamlandı{Style.RESET_ALL}")
        print(f"{Fore.RED}::{Style.RESET_ALL}{Fore.LIGHTBLACK_EX} Toplam URL bulundu: {len(self.ziyaret_edilen_url) + len(self.ziyaret_edilecek)}{Style.RESET_ALL}")
        print(f"{Fore.RED}::{Style.RESET_ALL}{Fore.LIGHTBLACK_EX} Toplam e-posta adresi bulundu: {len(set(self.sonuclar['eposta_adresleri']))}{Style.RESET_ALL}")
        print(f"{Fore.RED}::{Style.RESET_ALL}{Fore.LIGHTBLACK_EX} Toplam endpoint bulundu: {len(self.kesfedilen_endpointler)}{Style.RESET_ALL}")
        print(f"{Fore.RED}::{Style.RESET_ALL}{Fore.LIGHTBLACK_EX} Toplam benzersiz domain: {len(self.ziyaret_edilen_domainler)}{Style.RESET_ALL}")
        print(f"{Fore.RED}::{Style.RESET_ALL}{Fore.LIGHTBLACK_EX} Toplam benzersiz URL kaydedildi: {len(self.benzersiz_url_yollari)}{Style.RESET_ALL}")

        if self.param_dosyasi:
            print(f"{Fore.RED}::{Style.RESET_ALL}{Fore.LIGHTBLACK_EX} Toplam benzersiz parametre kaydedildi: {len(self.benzersiz_parametreler)}{Style.RESET_ALL}")

        if self.api_key_bul:
            print(f"{Fore.RED}::{Style.RESET_ALL}{Fore.LIGHTBLACK_EX} Toplam API Anahtarı bulundu: {len(self.bulunan_api_anahtarlari)}{Style.RESET_ALL}")
            if self.api_anahtari_dosyasi:
                print(f"{Fore.RED}::{Style.RESET_ALL}{Fore.LIGHTBLACK_EX} API Anahtarları kaydedildi: {self.api_anahtari_dosyasi}{Style.RESET_ALL}")
        if self.cikti_dosyasi:
            print(f"{Fore.RED}::{Style.RESET_ALL}{Fore.LIGHTBLACK_EX} URL'ler kaydedildi: {self.cikti_dosyasi}{Style.RESET_ALL}")
        if self.eposta_dosyasi:
            print(f"{Fore.RED}::{Style.RESET_ALL}{Fore.LIGHTBLACK_EX} E-postalar kaydedildi: {self.eposta_dosyasi}{Style.RESET_ALL}")
        if self.param_dosyasi:
            print(f"{Fore.RED}::{Style.RESET_ALL}{Fore.LIGHTBLACK_EX} Parametreler kaydedildi: {self.param_dosyasi}{Style.RESET_ALL}")
        print()

    def sonuclari_yazdir(self):
        print(f"\n{Fore.RED}::{Style.RESET_ALL}{Fore.LIGHTBLACK_EX} Bulunan E-postalar {Fore.RED}::{Style.RESET_ALL}")
        eposta_adresleri = set(self.sonuclar['eposta_adresleri'])
        if eposta_adresleri:
            for eposta in sorted(eposta_adresleri):
                print(f"{Fore.LIGHTBLACK_EX}    {eposta}{Style.RESET_ALL}")
        else:
            print(f"{Fore.LIGHTBLACK_EX}    E-posta adresi bulunamadı{Style.RESET_ALL}")

        if self.param_dosyasi and self.benzersiz_parametreler:
            print(f"\n{Fore.RED}::{Style.RESET_ALL}{Fore.LIGHTBLACK_EX} Bulunan Benzersiz Parametreler (ilk 20) {Fore.RED}::{Style.RESET_ALL}")
            for i, parametre in enumerate(sorted(self.benzersiz_parametreler)[:20]):
                print(f"{Fore.LIGHTBLACK_EX}    {parametre}{Style.RESET_ALL}")
            if len(self.benzersiz_parametreler) > 20:
                print(f"{Fore.LIGHTBLACK_EX}    ... ve {len(self.benzersiz_parametreler) - 20} daha parametre ({self.param_dosyasi} dosyasına bakın){Style.RESET_ALL}")
        if self.api_key_bul and self.bulunan_api_anahtarlari:
            print(f"\n{Fore.RED}::{Style.RESET_ALL}{Fore.LIGHTBLACK_EX} Bulunan API Anahtarları {Fore.RED}::{Style.RESET_ALL}")
            for api_anahtari in self.bulunan_api_anahtarlari[:10]:
                print(f"{Fore.RED}[KRİTİK] API anahtarı : {api_anahtari['tur']} <= {api_anahtari['url']}{Style.RESET_ALL}")
                print(f"{Fore.YELLOW}Değer: {api_anahtari['anahtar'][:50]}...{Style.RESET_ALL}")
                print(f"{Fore.LIGHTBLACK_EX}    İçerik: {api_anahtari['icerik']}{Style.RESET_ALL}")
                print()
            if len(self.bulunan_api_anahtarlari) > 10:
                print(f"{Fore.LIGHTBLACK_EX}    ... ve {len(self.bulunan_api_anahtarlari) - 10} daha API anahtarı ({self.api_anahtari_dosyasi} dosyasına bakın){Style.RESET_ALL}")

        if self.sonuclar['js_endpointleri']:
            print(f"\n{Fore.RED}::{Style.RESET_ALL}{Fore.LIGHTBLACK_EX} JavaScript'ten Bulunan Endpointler {Fore.RED}::{Style.RESET_ALL}")
            for js_endpoint in self.sonuclar['js_endpointleri'][:10]:
                print(f"{Fore.LIGHTBLACK_EX}    {js_endpoint['endpoint']} (kaynak: {js_endpoint['kaynak']}){Style.RESET_ALL}")
            if len(self.sonuclar['js_endpointleri']) > 10:
                print(f"{Fore.LIGHTBLACK_EX}    ... ve {len(self.sonuclar['js_endpointleri']) - 10} daha endpoint{Style.RESET_ALL}")

        if self.ziyaret_edilen_domainler:
            print(f"\n{Fore.RED}::{Style.RESET_ALL}{Fore.LIGHTBLACK_EX} Benzersiz Domainler {Fore.RED}::{Style.RESET_ALL}")
            domain_listesi = sorted(list(self.ziyaret_edilen_domainler))[:20]
            for domain in domain_listesi:
                print(f"{Fore.LIGHTBLACK_EX}    {domain}{Style.RESET_ALL}")
            if len(self.ziyaret_edilen_domainler) > 20:
                print(f"{Fore.LIGHTBLACK_EX}    ... ve {len(self.ziyaret_edilen_domainler) - 20} daha domain{Style.RESET_ALL}")

        print()

def main():
    parser = argparse.ArgumentParser(
        description='Gelişmiş Web Tarayıcı - Derin Link & Gizli Endpoint Keşfi',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""                                                                       
Örnekler:
  cheri -u https://bank.govm
  cheri -u https://bank.gov --output outputs.txt
  cheri --chain targets.txt --output sonuclar.txt
  cheri -u https://bank.gov --custom "api"
  cheri -u https://bank.gov --time-sec-mode
  cheri -u https://bank.gov --tor
  cheri -u https://bank.gov --https-only
  cheri -u https://bank.gov --user-agent "Özel Bot"
  cheri -u https://bank.gov --mail epostalar.txt
  cheri -u https://bank.gov --subfinder                                        
  cheri -u https://bank.gov --ignore-gapps
  cheri -u https://bank.gov --method POST
  cheri -u https://bank.gov --method ALL
  cheri -u https://bank.gov --skip-pick                                        
  cheri -u https://bank.gov --imitation
  cheri -u https://bank.gov --tasker
  cheri -u https://bank.gov --stay
  cheri -u https://bank.gov --find-keys
  cheri -u https://bank.gov --param params.txt
  cheri -u https://bank.gov --disable-ssl
        """
    )

    parser.add_argument('-u', '--url', help='Taranacak hedef URL')
    parser.add_argument('--chain', help='Hedef listesi dosyası (her satırda bir hedef)')
    parser.add_argument('--deeping', type=int, default=3, help='Maksimum tarama derinliği (varsayılan: 3)')
    parser.add_argument('--delay', type=float, default=0.2, help='İstekler arası bekleme süresi saniye (varsayılan: 0.2)')
    parser.add_argument('--timeout', type=int, default=10, help='İstek zaman aşımı saniye (varsayılan: 10)')
    parser.add_argument('--threads', type=int, default=30, help='Maksimum eşzamanlı thread (varsayılan: 30)')
    parser.add_argument('--output', help='URL\'ler için çıktı metin dosyası yolu (varsayılan: dosya çıktısı yok)')
    parser.add_argument('--mail', help='E-posta adresleri için çıktı dosyası (varsayılan: e-posta dosyası yok)')
    parser.add_argument('--custom', help='Özel domain filtresi (örn: "api" sadece "api" içeren URL\'leri işler)')
    parser.add_argument('--time-sec-mode', action='store_true', help='Zaman güvenlik modunu etkinleştir (her 1000 linkte 45 saniye duraklama)')
    parser.add_argument('--tor', action='store_true', help='İstekler için TOR proxy kullan (varsayılan: timeout=40s, threads=15)')
    parser.add_argument('--https-only', action='store_true', help='Sadece HTTPS URL\'lerini tara')
    parser.add_argument('--user-agent', help='Özel User-Agent string\'i')
    parser.add_argument('--subfinder', action='store_true', help='Alt domain bulmak için subfinder kullan')
    parser.add_argument('--ignore-gapps', action='store_true', help='Google ile ilgili URL\'leri görmezden gel')
    parser.add_argument('--method', choices=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS', 'ALL'], default='GET', help='Test edilecek HTTP method\'u (varsayılan: GET)')
    parser.add_argument('--skip-pick', action='store_true', help='Resim, CSS, font dosyalarını atla (.css, .jpg, .png, .gif, .woff, vb.)')
    parser.add_argument('--imitation', action='store_true', help='Her 50 istekte fingerprint ve kullanıcı aracını rastgele değiştir')
    parser.add_argument('--tasker', action='store_true', help='Endpoint\'leri bulduğu diğer sitelere test et')
    parser.add_argument('--stay', action='store_true', help='Sadece hedef domain\'de kal, diğer domain\'lere geçme')
    parser.add_argument('--find-keys', action='store_true', help='API anahtarlarını bul ve ekranda göster (varsayılan: kapalı)')
    parser.add_argument('--param', help='Benzersiz parametreleri kaydetmek için dosya yolu (örn: params.txt)')
    parser.add_argument('--disable-ssl', action='store_true', help='SSL doğrulamasını devre dışı bırak (güvenli değil!)')
    parser.add_argument('--no-content-limit', action='store_true', help='İçerik boyutu sınırı yok (sınırsız)')

    args = parser.parse_args()
    
    # URL veya chain parametresi kontrolü
    if not args.url and not args.chain:
        parser.error("En az birini belirtmelisiniz: --url veya --chain")
    
    # Chain modu
    if args.chain:
        try:
            with open(args.chain, 'r', encoding='utf-8') as f:
                hedefler = [line.strip() for line in f if line.strip()]
            
            if not hedefler:
                print(f"{Fore.RED}[-] Chain dosyası boş!{Style.RESET_ALL}")
                sys.exit(1)
            
            print(f"{Fore.GREEN}[+] {len(hedefler)} hedef yüklendi{Style.RESET_ALL}")
            
            for i, hedef in enumerate(hedefler):
                print(f"\n{Fore.CYAN}[{i+1}/{len(hedefler)}] {hedef} taranıyor...{Style.RESET_ALL}")
                
                try:
                    tarayici = WebTarayici(
                        hedef_url=hedef,
                        maksimum_derinlik=args.deeping,
                        bekleme_suresi=args.delay,
                        zaman_asimi=args.timeout,
                        kullanici_araci=args.user_agent,
                        maksimum_thread=args.threads,
                        cikti_dosyasi=args.output,
                        ozel_filtre=args.custom,
                        zaman_guvenlik_modu=args.time_sec_mode,
                        tor_kullan=args.tor,
                        sadece_https=args.https_only,
                        eposta_dosyasi=args.mail,
                        endpoint_testi=args.tasker,
                        subfinder_kullan=args.subfinder,
                        google_servisleri_gormezden_gel=args.ignore_gapps,
                        method=args.method,
                        resim_dosyalari_atla=args.skip_pick,
                        taklit_modu=args.imitation,
                        gorevlendirici=args.tasker,
                        sadece_hedef=args.stay,
                        api_key_bul=args.find_keys,
                        param_dosyasi=args.param,
                        disable_ssl=args.disable_ssl,
                        max_content_size=0 if args.no_content_limit else 10_000_000
                    )

                    tarayici.tara(chain_mode=True, chain_index=i, total_chains=len(hedefler))
                    tarayici.sonuclari_yazdir()
                    
                except KeyboardInterrupt:
                    print(f"\n{Fore.YELLOW}[!] Tarama kullanıcı tarafından durduruldu{Style.RESET_ALL}")
                    break
                except Exception as e:
                    print(f"{Fore.RED}[-] {hedef} için hata: {str(e)}{Style.RESET_ALL}")
                    continue
                
                # Hedefler arası bekleme
                if i < len(hedefler) - 1:
                    print(f"\n{Fore.YELLOW}[!] Bir sonraki hedefe geçmeden önce 3 saniye bekleniyor...{Style.RESET_ALL}")
                    time.sleep(3)
            
        except FileNotFoundError:
            print(f"{Fore.RED}[-] Chain dosyası bulunamadı: {args.chain}{Style.RESET_ALL}")
            sys.exit(1)
        except Exception as e:
            print(f"{Fore.RED}[-] Chain dosyası okuma hatası: {str(e)}{Style.RESET_ALL}")
            sys.exit(1)
    
    # Tek URL modu
    else:
        try:
            tarayici = WebTarayici(
                hedef_url=args.url,
                maksimum_derinlik=args.deeping,
                bekleme_suresi=args.delay,
                zaman_asimi=args.timeout,
                kullanici_araci=args.user_agent,
                maksimum_thread=args.threads,
                cikti_dosyasi=args.output,
                ozel_filtre=args.custom,
                zaman_guvenlik_modu=args.time_sec_mode,
                tor_kullan=args.tor,
                sadece_https=args.https_only,
                eposta_dosyasi=args.mail,
                endpoint_testi=args.tasker,
                subfinder_kullan=args.subfinder,
                google_servisleri_gormezden_gel=args.ignore_gapps,
                method=args.method,
                resim_dosyalari_atla=args.skip_pick,
                taklit_modu=args.imitation,
                gorevlendirici=args.tasker,
                sadece_hedef=args.stay,
                api_key_bul=args.find_keys,
                param_dosyasi=args.param,
                disable_ssl=args.disable_ssl,
                max_content_size=0 if args.no_content_limit else 10_000_000
            )

            tarayici.tara()
            tarayici.sonuclari_yazdir()

        except KeyboardInterrupt:
            print(f"\n{Fore.YELLOW}[!] Tarama kullanıcı tarafından durduruldu{Style.RESET_ALL}")
            try:
                if 'tarayici' in locals():
                    print(f"{Fore.YELLOW}[!] Kısmi sonuçlar kaydediliyor...{Style.RESET_ALL}")
                    if args.output:
                        tarayici.epostalari_cikti_dosyasina_kaydet()
                    if args.mail:
                        tarayici.tum_epostalari_dosyaya_kaydet()
                    tarayici.sonuclari_yazdir()
                    if args.output:
                        print(f"{Fore.GREEN}[✓] URL\'ler kaydedildi: {args.output}{Style.RESET_ALL}")
                    if args.mail:
                        print(f"{Fore.GREEN}[✓] E-postalar kaydedildi: {args.mail}{Style.RESET_ALL}")
                    if args.param:
                        print(f"{Fore.GREEN}[✓] Parametreler kaydedildi: {args.param}{Style.RESET_ALL}")
            except Exception as e:
                print(f"{Fore.RED}[-] Kısmi sonuçları kaydetme hatası: {str(e)}{Style.RESET_ALL}")

            sys.exit(0)
        except Exception as e:
            print(f"\n{Fore.RED}[!] Ölümcül hata: {str(e)}{Style.RESET_ALL}")
            sys.exit(1)

if __name__ == '__main__':
    main()
