"""
core/template_engine.py — Email Template Engine v3 (Multi-Product Professional)
Sektöre göre profesyonel HTML email şablonları — çoklu ürün görseli, eşleşen arka plan.
Tablo-bazlı layout (Outlook/Gmail/Apple Mail uyumlu).
"""
from core.logger import get_logger

log = get_logger("template_engine")

# ─── IMAGE ASSETS (Teltonika resmi wiki'den) ─────────────────────
IMAGES = {
    "logo": "https://www.fleettrackholland.nl/logo512.png",
    "og": "https://www.fleettrackholland.nl/og-image.png",
    # Ürün görselleri — tümü wiki.teltonika-gps.com'dan
    "fmc130": "https://wiki.teltonika-gps.com/images/5/51/Screenshot_2023-12-18_090141.png",
    "fmb920": "https://wiki.teltonika-gps.com/images/1/1e/FMB920-side-2024-01-11.png",
    "fmb140": "https://wiki.teltonika-gps.com/images/d/d6/FMB140_BL_logo_4000X4000_02.png",
    "fmc650": "https://wiki.teltonika-gps.com/images/8/83/FMC650-MBX50-front-2023-12-29.png",
}

# Arka plan renkleri — görsel kenar rengine eşleştirildi
IMG_BG = {
    "fmc130": "#e8e8e8",   # açık gri kenar
    "fmb920": "#ffffff",   # beyaz kenar
    "fmb140": "#ffffff",   # beyaz kenar
    "fmc650": "#e8e8e8",   # açık gri kenar
}

# ─── REUSABLE SNIPPETS ───────────────────────────────────────────

_HEAD = """<!DOCTYPE html>
<html lang="nl" xmlns="http://www.w3.org/1999/xhtml">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="X-UA-Compatible" content="IE=edge">
<title>FleetTrack Holland</title>
</head>"""

_TAIL = """</table>
</td></tr>
</table>

</body>
</html>"""

# ─── MULTI-PRODUCT IMAGE ROWS ────────────────────────────────────
# 3 ürün yan yana — gri arka plan (FMC130 + FMC650 eşleşir)
_PRODUCTS_3_GREY = """
  <!-- Product lineup — 3 devices -->
  <tr><td style="padding:20px 16px;background-color:#e8e8e8;border-bottom:1px solid #d0d0d0;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
    <tr>
      <td align="center" width="33%" style="padding:4px;">
        <img src="{img_fmc130}" alt="FMC130" style="height:70px;width:auto;display:inline-block;" />
        <p style="margin:6px 0 0;font-size:10px;color:#555;font-weight:600;">FMC130</p>
      </td>
      <td align="center" width="33%" style="padding:4px;">
        <img src="{img_fmb920}" alt="FMB920" style="height:70px;width:auto;display:inline-block;" />
        <p style="margin:6px 0 0;font-size:10px;color:#555;font-weight:600;">FMB920</p>
      </td>
      <td align="center" width="33%" style="padding:4px;">
        <img src="{img_fmc650}" alt="FMC650" style="height:70px;width:auto;display:inline-block;" />
        <p style="margin:6px 0 0;font-size:10px;color:#555;font-weight:600;">FMC650</p>
      </td>
    </tr>
    </table>
    <p style="margin:8px 0 0;font-size:10px;color:#777;text-align:center;">Teltonika GPS Trackers — Professionele Vlootoplossingen</p>
  </td></tr>"""

# 2 ürün yan yana — beyaz arka plan (FMB920 + FMB140 eşleşir)
_PRODUCTS_2_WHITE = """
  <!-- Product lineup — 2 devices -->
  <tr><td style="padding:20px 24px;background-color:#ffffff;border-top:1px solid #eee;border-bottom:1px solid #eee;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
    <tr>
      <td align="center" width="50%" style="padding:8px;">
        <img src="{img_fmb920}" alt="FMB920" style="height:75px;width:auto;display:inline-block;" />
        <p style="margin:6px 0 0;font-size:10px;color:#555;font-weight:600;">FMB920</p>
        <p style="margin:2px 0 0;font-size:9px;color:#999;">Compact tracker</p>
      </td>
      <td align="center" width="50%" style="padding:8px;">
        <img src="{img_fmb140}" alt="FMB140" style="height:75px;width:auto;display:inline-block;" />
        <p style="margin:6px 0 0;font-size:10px;color:#555;font-weight:600;">FMB140</p>
        <p style="margin:2px 0 0;font-size:9px;color:#999;">Advanced fleet</p>
      </td>
    </tr>
    </table>
    <p style="margin:8px 0 0;font-size:10px;color:#888;text-align:center;">Teltonika — Professionele GPS Tracking</p>
  </td></tr>"""

# Enkele product + mini product — grijs (voor Security template)
_PRODUCT_SECURITY = """
  <!-- Product section — security focus -->
  <tr><td style="padding:20px 24px;background-color:#e8e8e8;border-top:1px solid #d0d0d0;border-bottom:1px solid #d0d0d0;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
    <tr>
      <td align="center" width="50%" style="padding:4px;">
        <img src="{img_fmc130}" alt="FMC130" style="height:80px;width:auto;display:inline-block;" />
        <p style="margin:6px 0 0;font-size:10px;color:#555;font-weight:600;">FMC130</p>
        <p style="margin:2px 0 0;font-size:9px;color:#777;">Diefstalpreventie</p>
      </td>
      <td align="center" width="50%" style="padding:4px;">
        <img src="{img_fmc650}" alt="FMC650" style="height:80px;width:auto;display:inline-block;" />
        <p style="margin:6px 0 0;font-size:10px;color:#555;font-weight:600;">FMC650</p>
        <p style="margin:2px 0 0;font-size:9px;color:#777;">Zwaar materieel</p>
      </td>
    </tr>
    </table>
  </td></tr>"""

# Minimal follow-up — inline product row
_PRODUCT_INLINE = """
  <!-- Inline product + CTA -->
  <tr><td style="padding:16px 28px;background-color:#e8e8e8;border-top:1px solid #d0d0d0;border-bottom:1px solid #d0d0d0;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
    <tr>
      <td width="75" style="padding-right:12px;">
        <img src="{img_fmc130}" alt="FMC130" style="height:55px;width:auto;display:block;" />
      </td>
      <td style="vertical-align:middle;">
        <p style="margin:0 0 3px;font-size:13px;font-weight:600;color:#333;">Teltonika FMC130</p>
        <p style="margin:0;font-size:11px;color:#777;">Professionele GPS tracker — vanaf <strong style="color:#CC0000;">€9,95/mnd</strong></p>
      </td>
      <td width="130" align="right" style="vertical-align:middle;">
        <a href="{cta_url}" style="display:inline-block;padding:10px 18px;background:#CC0000;color:#fff;text-decoration:none;border-radius:6px;font-weight:600;font-size:12px;">{cta_text}</a>
      </td>
    </tr>
    </table>
  </td></tr>"""

# ─── TEMPLATE CATALOG ─────────────────────────────────────────

TEMPLATES = {
    # ═══════════════════════════════════════════════════════════════
    # 0. BREVO OFFICIAL — Kullanıcının Brevo'da oluşturduğu template (VARSAYILAN)
    #    Logo, fontlar, renkler, hiçbir şey değiştirilmedi.
    # ═══════════════════════════════════════════════════════════════
    "brevo_official": {
        "name": "Brevo Official",
        "description": "Kullanıcının Brevo'da oluşturduğu orijinal template — siyah arka plan, Montserrat + Playfair Display",
        "sectors": ["default"],
        "html": """<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd"><html xmlns="http://www.w3.org/1999/xhtml" xmlns:v="urn:schemas-microsoft-com:vml" xmlns:o="urn:schemas-microsoft-com:office:office"><head><meta content="text/html;charset=UTF-8" http-equiv="Content-Type"><meta http-equiv="Content-Type" content="text/html; charset=utf-8"/><meta http-equiv="X-UA-Compatible" content="IE=edge"/><meta name="format-detection" content="telephone=no"/><meta name="viewport" content="width=device-width, initial-scale=1.0"/><title>GPS TRACKING</title><style type="text/css" emogrify="no">#outlook a {{ padding:0; }} .ExternalClass {{ width:100%; }} .ExternalClass, .ExternalClass p, .ExternalClass span, .ExternalClass font, .ExternalClass td, .ExternalClass div {{ line-height: 100%; }} table td {{ border-collapse: collapse; mso-line-height-rule: exactly; }} .editable.image {{ font-size: 0 !important; line-height: 0 !important; }} .nl2go_preheader {{ display: none !important; mso-hide:all !important; mso-line-height-rule: exactly; visibility: hidden !important; line-height: 0px !important; font-size: 0px !important; }} body {{ width:100% !important; -webkit-text-size-adjust:100%; -ms-text-size-adjust:100%; margin:0; padding:0; }} img {{ outline:none; text-decoration:none; -ms-interpolation-mode: bicubic; }} a img {{ border:none; }} table {{ border-collapse:collapse; mso-table-lspace:0pt; mso-table-rspace:0pt; }} th {{ font-weight: normal; text-align: left; }} *[class="gmail-fix"] {{ display: none !important; }} </style><style type="text/css" emogrify="no"> @media (max-width: 600px) {{ .gmx-killpill {{ content: ' \\03D1';}} }} </style><style type="text/css" emogrify="no">@media (max-width: 600px) {{ .gmx-killpill {{ content: ' \\03D1';}} .r0-o {{ border-style: solid !important; margin: 0 auto 0 auto !important; width: 100% !important }} .r1-i {{ background-color: transparent !important }} .r2-c {{ box-sizing: border-box !important; text-align: center !important; valign: top !important; width: 320px !important }} .r3-o {{ border-style: solid !important; margin: 0 auto 0 auto !important; width: 320px !important }} .r4-i {{ padding-bottom: 5px !important; padding-top: 5px !important }} .r5-c {{ box-sizing: border-box !important; display: block !important; valign: top !important; width: 100% !important }} .r6-o {{ border-style: solid !important; width: 100% !important }} .r7-i {{ padding-left: 10px !important; padding-right: 10px !important; padding-top: 20px !important; text-align: center !important }} .r8-i {{ background-color: #020202 !important }} .r9-c {{ box-sizing: border-box !important; text-align: center !important; valign: top !important; width: 100% !important }} .r10-i {{ background-color: #020202 !important; padding-top: 30px !important }} .r11-o {{ border-style: solid !important; margin: 0 auto 0 auto !important; width: 200px !important }} .r12-i {{ background-color: #020202 !important; padding-left: 10px !important; padding-right: 10px !important; padding-top: 40px !important }} .r13-o {{ border-style: solid !important; margin: 0 auto 0 0 !important; width: 100% !important }} .r14-i {{ text-align: center !important }} .r15-i {{ background-color: #020202 !important; padding-top: 10px !important }} .r16-i {{ background-color: #020202 !important; padding-left: 10px !important; padding-right: 10px !important; padding-top: 20px !important }} .r17-o {{ border-style: solid !important; margin: 0 auto 0 auto !important; width: 270px !important }} .r18-r {{ border-color: #ffffff !important; border-radius: 0px !important; border-width: 1px !important; padding-bottom: 6px !important; padding-top: 6px !important; text-align: center !important; width: 268px !important }} .r19-i {{ padding-top: 40px !important }} .r20-o {{ border-style: solid !important; border-top-width: 2px !important; margin: 0 auto 0 auto !important; width: 100% !important }} .r21-i {{ background-color: #020202 !important; padding-bottom: 35px !important; padding-top: 35px !important }} .r22-c {{ box-sizing: border-box !important; display: block !important; valign: bottom !important; width: 100% !important }} .r23-i {{ padding-left: 0px !important; padding-right: 0px !important }} .r24-c {{ box-sizing: border-box !important; text-align: center !important; width: 100% !important }} .r25-i {{ font-size: 0px !important; padding-bottom: 0px !important; padding-left: 116px !important; padding-right: 117px !important; padding-top: 0px !important }} .r26-c {{ box-sizing: border-box !important; width: 32px !important }} .r27-o {{ border-style: solid !important; margin-right: 15px !important; width: 32px !important }} .r28-o {{ border-style: solid !important; margin-right: 0px !important; width: 32px !important }} .r29-c {{ box-sizing: border-box !important; padding-top: 20px !important; text-align: center !important; valign: top !important; width: 100% !important }} .r30-i {{ padding-top: 20px !important; text-align: center !important }} body {{ -webkit-text-size-adjust: none }} .nl2go-responsive-hide {{ display: none }} .nl2go-body-table {{ min-width: unset !important }} .mobshow {{ height: auto !important; overflow: visible !important; max-height: unset !important; visibility: visible !important }} .resp-table {{ display: inline-table !important }} .magic-resp {{ display: table-cell !important }} }} </style><!--[if !mso]><!--><style type="text/css" emogrify="no">@import url("https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;900&display=swap"); @import url("https://fonts.googleapis.com/css2?family=Montserrat:wght@400;700&display=swap"); </style><!--<![endif]--><style type="text/css">p, h1, h2, h3, h4, ol, ul, li {{ margin: 0; }} .nl2go-default-textstyle {{ color: #ffffff; font-family: Montserrat, Arial, Helvetica, sans-serif; font-size: 24px; font-weight: 400; line-height: 1.15; word-break: break-word }} .default-button {{ color: #ffffff; font-family: Montserrat, Arial, Helvetica, sans-serif; font-size: 20px; font-style: normal; font-weight: normal; line-height: 1.15; text-decoration: none; word-break: break-word }} a, a:link {{ color: #807B7B; text-decoration: none }} .default-heading1 {{ color: #ffffff; font-family: Montserrat, Arial, Helvetica, sans-serif; font-size: 24px; font-weight: 400; word-break: break-word }} .default-heading2 {{ color: #ffffff; font-family: Montserrat, Arial, Helvetica, sans-serif; font-size: 32px; font-weight: 400; word-break: break-word }} .default-heading3 {{ color: #ffffff; font-family: Montserrat, Arial, Helvetica, sans-serif; font-size: 24px; font-weight: 400; word-break: break-word }} .default-heading4 {{ color: #ffffff; font-family: Montserrat, Arial, Helvetica, sans-serif; font-size: 18px; font-weight: 400; word-break: break-word }} a[x-apple-data-detectors] {{ color: inherit !important; text-decoration: inherit !important; font-size: inherit !important; font-family: inherit !important; font-weight: inherit !important; line-height: inherit !important; }} .no-show-for-you {{ border: none; display: none; float: none; font-size: 0; height: 0; line-height: 0; max-height: 0; mso-hide: all; overflow: hidden; table-layout: fixed; visibility: hidden; width: 0; }} </style><!--[if mso]><xml> <o:OfficeDocumentSettings> <o:AllowPNG/> <o:PixelsPerInch>96</o:PixelsPerInch> </o:OfficeDocumentSettings> </xml><![endif]--><style type="text/css">a:link{{color: #807b7b; text-decoration: none;}}</style></head><body bgcolor="#020202" text="#ffffff" link="#807B7B" yahoo="fix" style="background-color: #020202;"> <table cellspacing="0" cellpadding="0" border="0" role="presentation" class="nl2go-body-table" width="100%" style="background-color: #020202; width: 100%;"><tbody><tr><td> <table cellspacing="0" cellpadding="0" border="0" role="presentation" width="100%" align="center" class="r0-o" style="table-layout: fixed; width: 100%;"><tbody><tr><td valign="top" class="r1-i" style="background-color: transparent;"> <table cellspacing="0" cellpadding="0" border="0" role="presentation" width="600" align="center" class="r3-o" style="table-layout: fixed;"><tbody><tr><td class="r4-i" style="padding-bottom: 5px; padding-top: 5px;"> <table width="100%" cellspacing="0" cellpadding="0" border="0" role="presentation"><tbody><tr><th width="100%" valign="top" class="r5-c" style="font-weight: normal;"> <table cellspacing="0" cellpadding="0" border="0" role="presentation" width="100%" align="center" class="r0-o" style="table-layout: fixed; width: 100%;"><tbody><tr><td align="center" class="r7-i nl2go-default-textstyle" style="color: #fff; font-family: Montserrat,Arial,Helvetica,sans-serif; font-size: 24px; font-weight: 400; line-height: 1.15; word-break: break-word; padding-left: 30px; padding-right: 30px; padding-top: 20px; text-align: center;"> <div><p style="margin: 0;"><span style="font-size: 12px; color: #807b7b;">View in browser</span></p></div> </td> </tr></tbody></table></th> </tr></tbody></table></td> </tr></tbody></table><table cellspacing="0" cellpadding="0" border="0" role="presentation" width="600" align="center" class="r3-o" style="table-layout: fixed; width: 600px;"><tbody><tr><td valign="top" class="r8-i" style="background-color: #020202;"> <table cellspacing="0" cellpadding="0" border="0" role="presentation" width="100%" align="center" class="r0-o" style="table-layout: fixed; width: 100%;"><tbody><tr><th width="100%" valign="top" class="r9-c" style="font-weight: normal;"> <table cellspacing="0" cellpadding="0" border="0" role="presentation" width="100%" align="center" class="r0-o" style="table-layout: fixed; width: 100%;"><tbody><tr><td class="r10-i" style="background-color: #020202; padding-top: 30px;"> <table cellspacing="0" cellpadding="0" border="0" role="presentation" width="200" align="center" class="r11-o" style="table-layout: fixed; width: 200px;"><tbody><tr><td style="font-size: 0px; line-height: 0px;"> <img src="https://675841.img.track.brevo.com/675841/bca4b0ab-2f3b-4886-90e8-09756184ff74.png" width="200" border="0" style="display: block; width: 100%;" alt="FleetTrack Holland"/> </td> </tr></tbody></table></td> </tr></tbody></table></th> </tr></tbody></table> <table cellspacing="0" cellpadding="0" border="0" role="presentation" width="100%" align="center" class="r0-o" style="table-layout: fixed; width: 100%;"><tbody><tr><th width="100%" valign="top" class="r9-c" style="font-weight: normal;"> <table cellspacing="0" cellpadding="0" border="0" role="presentation" width="100%" align="center" class="r0-o" style="table-layout: fixed; width: 100%;"><tbody><tr><td align="left" class="r12-i nl2go-default-textstyle" style="background-color: #020202; color: #fff; font-family: Montserrat,Arial,Helvetica,sans-serif; font-size: 24px; font-weight: 400; line-height: 1.15; word-break: break-word; padding-left: 30px; padding-right: 30px; padding-top: 40px; text-align: left;"> <div><h2 class="default-heading2" style="margin: 0; color: #fff; font-family: Montserrat,Arial,Helvetica,sans-serif; font-size: 32px; font-weight: 400; word-break: break-word; text-align: center;"><span style="font-size: 40px;">{headline}</span></h2></div> </td> </tr></tbody></table></th> </tr></tbody></table> <table cellspacing="0" cellpadding="0" border="0" role="presentation" width="100%" align="left" class="r13-o" style="table-layout: fixed; width: 100%;"><tbody><tr><th width="100%" valign="top" class="r9-c" style="font-weight: normal;"> <table cellspacing="0" cellpadding="0" border="0" role="presentation" width="100%" align="center" class="r0-o" style="table-layout: fixed; width: 100%;"><tbody><tr><td class="r10-i" style="background-color: #020202; padding-top: 30px;"> <table cellspacing="0" cellpadding="0" border="0" role="presentation" width="100%" align="center" class="r0-o" style="table-layout: fixed; width: 100%;"><tbody><tr><td style="font-size: 0px; line-height: 0px;" class="r14-i" align="center"> <img src="https://675841.img.track.brevo.com/675841/53b92cb2-e300-47f5-aae4-071a93132e08.png" width="600" border="0" style="display: block; width: 100%;" alt="Fleet Vehicles"/> </td> </tr></tbody></table></td> </tr></tbody></table></th> </tr></tbody></table> <table cellspacing="0" cellpadding="0" border="0" role="presentation" width="100%" align="center" class="r0-o" style="table-layout: fixed; width: 100%;"><tbody><tr><th width="100%" valign="top" class="r9-c" style="font-weight: normal;"> <table cellspacing="0" cellpadding="0" border="0" role="presentation" width="100%" align="center" class="r0-o" style="table-layout: fixed; width: 100%;"><tbody><tr><td align="center" class="r12-i nl2go-default-textstyle" style="background-color: #020202; color: #fff; font-family: Montserrat,Arial,Helvetica,sans-serif; font-size: 24px; font-weight: 400; line-height: 1.15; word-break: break-word; padding-left: 30px; padding-right: 30px; padding-top: 40px; text-align: center;"> <div>{body_content}</div> </td> </tr></tbody></table></th> </tr></tbody></table> <table cellspacing="0" cellpadding="0" border="0" role="presentation" width="100%" align="center" class="r0-o" style="table-layout: fixed; width: 100%;"><tbody><tr><th width="100%" valign="top" class="r9-c" style="font-weight: normal;"> <table cellspacing="0" cellpadding="0" border="0" role="presentation" width="100%" align="center" class="r0-o" style="table-layout: fixed; width: 100%;"><tbody><tr><td class="r15-i" style="background-color: #020202; padding-top: 10px;"> <table cellspacing="0" cellpadding="0" border="0" role="presentation" width="100%" align="center" class="r0-o" style="table-layout: fixed; width: 100%;"><tbody><tr><td class="r12-i" style="background-color: #020202; padding-left: 30px; padding-right: 30px; padding-top: 40px;"> <table cellspacing="0" cellpadding="0" border="0" role="presentation" width="270" align="center" class="r17-o" style="table-layout: fixed; width: 270px;"><tbody><tr><td class="r18-r default-button" bgcolor="transparent" style="background-color: transparent; border-color: #fff; border-radius: 0px; border-style: solid; border-width: 1px; color: #fff; font-family: Montserrat,Arial,Helvetica,sans-serif; font-size: 20px; font-style: normal; font-weight: normal; line-height: 1.15; padding-bottom: 6px; padding-top: 6px; text-align: center; text-decoration: none; word-break: break-word;"> <a href="{cta_url}" class="default-button" style="color: #fff; font-family: Montserrat,Arial,Helvetica,sans-serif; font-size: 20px; font-style: normal; font-weight: normal; line-height: 1.15; text-decoration: none; word-break: break-word;">{cta_text}</a> </td> </tr></tbody></table></td> </tr></tbody></table></td> </tr></tbody></table></th> </tr></tbody></table> <table cellspacing="0" cellpadding="0" border="0" role="presentation" width="100%" align="center" class="r0-o" style="table-layout: fixed; width: 100%;"><tbody><tr><td class="r19-i" style="padding-top: 40px;"> <table cellspacing="0" cellpadding="0" border="0" role="presentation" width="100%" align="center" class="r20-o" style="border-top: 2px solid #3d3b3b; table-layout: fixed; width: 100%;"><tbody><tr><td class="r21-i" style="background-color: #020202; padding-bottom: 35px; padding-top: 35px;"> <table width="100%" cellspacing="0" cellpadding="0" border="0" role="presentation"><tbody><tr><th width="100%" valign="bottom" class="r22-c" style="font-weight: normal;"> <table cellspacing="0" cellpadding="0" border="0" role="presentation" width="100%" align="center" class="r0-o" style="table-layout: fixed; width: 100%;"><tbody><tr><td valign="top" class="r23-i"> <table cellspacing="0" cellpadding="0" border="0" role="presentation" width="100%" align="center" class="r0-o" style="table-layout: fixed; width: 100%;"><tbody><tr><td class="r24-c" style="text-align: center;"> <table cellspacing="0" cellpadding="0" border="0" role="presentation" align="center" class="resp-table" style="display: table-cell;"><tbody><tr><td class="r26-c" style="width: 32px;"> <table cellspacing="0" cellpadding="0" border="0" role="presentation" width="32" align="left" class="r27-o" style="table-layout: fixed; width: 32px; margin-right: 15px;"><tbody><tr><td style="font-size: 0px; line-height: 0px;"> <a href="https://www.instagram.com/fleettrackholland/"> <img src="https://675841.img.track.brevo.com/675841/6533f86e-b35f-42ae-848e-2495d0339ab3.png" width="32" border="0" style="display: block; width: 100%;" alt="Instagram"/> </a> </td> </tr></tbody></table></td> <td class="r26-c" style="width: 32px;"> <table cellspacing="0" cellpadding="0" border="0" role="presentation" width="32" align="left" class="r28-o" style="table-layout: fixed; width: 32px; margin-right: 300px;"><tbody><tr><td style="font-size: 0px; line-height: 0px;"> <a href="https://www.linkedin.com/company/fleet-track-holland"> <img src="https://675841.img.track.brevo.com/675841/004d8f1e-6240-41ff-80bb-644aa2d6b384.png" width="32" border="0" style="display: block; width: 100%;" alt="LinkedIn"/> </a> </td> <td style="color: #807B7B; font-family: Montserrat,Arial,Helvetica,sans-serif; font-size: 16px; font-weight: 400; line-height: 1.15; word-break: break-word; text-align: left; vertical-align: bottom;">Fleet Track Holland<br/>Rotterdam<br/>info@fleettrackholland.nl</td> </tr></tbody></table></td> </tr></tbody></table></td> </tr></tbody></table> <table cellspacing="0" cellpadding="0" border="0" role="presentation" width="100%" align="center" class="r0-o" style="table-layout: fixed; width: 100%;"><tbody><tr><td align="left" class="r29-c nl2go-default-textstyle" style="color: #fff; font-family: Montserrat,Arial,Helvetica,sans-serif; font-size: 24px; font-weight: 400; line-height: 1.15; word-break: break-word; padding-top: 20px; text-align: left;"> <div><p style="margin: 0;"><span style="font-size: 14px;"><a href="https://www.fleettrackholland.nl/privacy" style="color: #807b7b; text-decoration: none;">Privacy</a>&nbsp;&nbsp;&nbsp;&nbsp;<a href="https://www.fleettrackholland.nl" style="color: #807b7b; text-decoration: none;">Website</a></span></p><p style="margin: 0;"><span style="font-size: 14px;"><a href="{unsubscribe_url}" style="color: #807b7b; text-decoration: none;">Uitschrijven</a></span></p></div> </td> </tr></tbody></table></th> </tr></tbody></table></td> </tr></tbody></table></td> </tr></tbody></table></td> </tr></tbody></table></td> </tr></tbody></table></td> </tr></tbody></table></body></html>""",
    },


    # ═══════════════════════════════════════════════════════════════
    # 0b. BREVO PRODUCT — Kullanıcının Brevo'daki ürün bazlı template
    #     Logo, fontlar, renkler, görseller hiçbir şey değiştirilmedi.
    # ═══════════════════════════════════════════════════════════════
    "brevo_product": {
        "name": "Brevo Product",
        "description": "Ürün bazlı template — FTC961, DashCam, Best Sellers, PROMO26",
        "sectors": ["product"],
        "html": """<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd"><html xmlns="http://www.w3.org/1999/xhtml" xmlns:v="urn:schemas-microsoft-com:vml" xmlns:o="urn:schemas-microsoft-com:office:office"><head><meta content="text/html;charset=UTF-8" http-equiv="Content-Type"><meta http-equiv="Content-Type" content="text/html; charset=utf-8"/><meta http-equiv="X-UA-Compatible" content="IE=edge"/><meta name="format-detection" content="telephone=no"/><meta name="viewport" content="width=device-width, initial-scale=1.0"/><title>Gps Trackker Nederland</title><style type="text/css" emogrify="no">#outlook a {{ padding:0; }} .ExternalClass {{ width:100%; }} .ExternalClass, .ExternalClass p, .ExternalClass span, .ExternalClass font, .ExternalClass td, .ExternalClass div {{ line-height: 100%; }} table td {{ border-collapse: collapse; mso-line-height-rule: exactly; }} .editable.image {{ font-size: 0 !important; line-height: 0 !important; }} .nl2go_preheader {{ display: none !important; mso-hide:all !important; mso-line-height-rule: exactly; visibility: hidden !important; line-height: 0px !important; font-size: 0px !important; }} body {{ width:100% !important; -webkit-text-size-adjust:100%; -ms-text-size-adjust:100%; margin:0; padding:0; }} img {{ outline:none; text-decoration:none; -ms-interpolation-mode: bicubic; }} a img {{ border:none; }} table {{ border-collapse:collapse; mso-table-lspace:0pt; mso-table-rspace:0pt; }} th {{ font-weight: normal; text-align: left; }} *[class="gmail-fix"] {{ display: none !important; }} </style><style type="text/css" emogrify="no"> @media (max-width: 600px) {{ .gmx-killpill {{ content: ' \03D1';}} }} </style><style type="text/css" emogrify="no">@media (max-width: 600px) {{ .gmx-killpill {{ content: ' \03D1';}} .r0-o {{ border-style: solid !important; margin: 0 auto 0 auto !important; width: 100% !important }} .r1-i {{ background-color: transparent !important }} .r2-c {{ box-sizing: border-box !important; text-align: center !important; valign: top !important; width: 100% !important }} .r3-i {{ padding-bottom: 5px !important; padding-top: 5px !important }} .r4-c {{ box-sizing: border-box !important; display: block !important; valign: top !important; width: 100% !important }} .r5-o {{ border-style: solid !important; width: 100% !important }} .r6-i {{ padding-left: 10px !important; padding-right: 10px !important; text-align: center !important }} .r7-i {{ background-color: #ffffff !important }} .r8-i {{ padding-bottom: 80px !important; padding-left: 15px !important; padding-right: 15px !important; padding-top: 20px !important }} .r9-i {{ padding-left: 0px !important; padding-right: 0px !important }} .r10-o {{ border-style: solid !important; margin: 0 auto 0 auto !important; margin-bottom: 0px !important; margin-top: 0px !important; width: 100% !important }} .r11-i {{ background-color: #f5f5f5 !important }} .r12-i {{ padding-bottom: 60px !important; padding-left: 0px !important; padding-right: 0px !important; padding-top: 60px !important }} .r13-c {{ box-sizing: border-box !important; padding-bottom: 0px !important; padding-left: 0px !important; padding-right: 0px !important; padding-top: 0px !important; text-align: center !important; valign: top !important; width: 100% !important }} .r14-c {{ box-sizing: border-box !important; text-align: left !important; valign: top !important; width: 100% !important }} .r15-o {{ border-style: solid !important; margin: 0 auto 0 0 !important; width: 100% !important }} .r16-i {{ padding-bottom: 0px !important; padding-top: 8px !important; text-align: center !important }} .r17-c {{ box-sizing: border-box !important; padding: 0 !important; text-align: center !important; valign: top !important; width: 100% !important }} .r18-o {{ border-style: solid !important; margin: 0 auto 0 auto !important; margin-bottom: 0px !important; margin-top: 40px !important; width: 100% !important }} .r19-i {{ padding: 0 !important; text-align: center !important }} .r20-r {{ background-color: #222222 !important; border-color: #666666 !important; border-radius: 4px !important; border-width: 0px !important; box-sizing: border-box; height: initial !important; padding: 0 !important; padding-bottom: 12px !important; padding-top: 12px !important; text-align: center !important; width: 100% !important }} .r21-i {{ padding-bottom: 20px !important; padding-left: 16px !important; padding-right: 16px !important; padding-top: 40px !important }} .r22-i {{ padding-bottom: 0px !important; padding-left: 0px !important; padding-right: 0px !important; padding-top: 0px !important; text-align: left !important }} .r23-i {{ padding-bottom: 0px !important; padding-top: 5px !important; text-align: left !important }} .r24-i {{ padding-bottom: 40px !important; padding-left: 16px !important; padding-right: 16px !important; padding-top: 20px !important }} .r25-i {{ padding-bottom: 0px !important; padding-left: 0px !important; padding-right: 0px !important; padding-top: 0px !important }} .r26-c {{ box-sizing: border-box !important; padding-bottom: 0px !important; padding-left: 0px !important; padding-right: 0px !important; padding-top: 10px !important; text-align: left !important; valign: top !important; width: 100% !important }} .r27-c {{ box-sizing: border-box !important; padding-bottom: 0px !important; padding-top: 5px !important; text-align: left !important; valign: top !important; width: 100% !important }} .r28-o {{ border-style: solid !important; margin: 0 auto 0 auto !important; margin-bottom: 0px !important; margin-top: 15px !important; width: 100% !important }} .r29-i {{ background-color: #f5f5f5 !important; padding-bottom: 40px !important; padding-left: 15px !important; padding-right: 15px !important; padding-top: 40px !important }} .r30-i {{ padding-bottom: 0px !important; padding-left: 0px !important; padding-right: 0px !important; padding-top: 0px !important; text-align: center !important }} .r31-i {{ padding-bottom: 20px !important; padding-top: 20px !important; text-align: center !important }} .r32-i {{ padding-bottom: 20px !important; padding-left: 15px !important; padding-right: 15px !important; padding-top: 80px !important }} .r33-i {{ padding-bottom: 10px !important }} .r34-c {{ box-sizing: border-box !important; padding-bottom: 10px !important; padding-left: 0px !important; padding-right: 0px !important; padding-top: 0px !important; text-align: center !important; valign: top !important; width: 100% !important }} .r35-c {{ box-sizing: border-box !important; padding-bottom: 0px !important; padding-left: 0px !important; padding-right: 0px !important; padding-top: 10px !important; text-align: center !important; valign: top !important; width: 100% !important }} body {{ -webkit-text-size-adjust: none }} .nl2go-responsive-hide {{ display: none }} .nl2go-body-table {{ min-width: unset !important }} .mobshow {{ height: auto !important; overflow: visible !important; max-height: unset !important; visibility: visible !important }} .resp-table {{ display: inline-table !important }} .magic-resp {{ display: table-cell !important }} }} </style><style type="text/css">p, h1, h2, h3, h4, ol, ul, li {{ margin: 0; }} .nl2go-default-textstyle {{ color: #414141; font-family: Arial; font-size: 16px; line-height: 1.5; word-break: break-word }} .default-button {{ color: #ffffff; font-family: Arial; font-size: 16px; font-style: normal; font-weight: normal; line-height: 1.15; text-decoration: none; word-break: break-word }} a, a:link {{ color: #666666; text-decoration: underline }} .default-heading1 {{ color: #414141; font-family: Arial; font-size: 36px; font-weight: 400; word-break: break-word }} .default-heading2 {{ color: #414141; font-family: Arial; font-size: 32px; font-weight: 400; word-break: break-word }} .default-heading3 {{ color: #1F2D3D; font-family: Arial; font-size: 24px; font-weight: 400; word-break: break-word }} .default-heading4 {{ color: #1F2D3D; font-family: Arial; font-size: 18px; font-weight: 400; word-break: break-word }} a[x-apple-data-detectors] {{ color: inherit !important; text-decoration: inherit !important; font-size: inherit !important; font-family: inherit !important; font-weight: inherit !important; line-height: inherit !important; }} .no-show-for-you {{ border: none; display: none; float: none; font-size: 0; height: 0; line-height: 0; max-height: 0; mso-hide: all; overflow: hidden; table-layout: fixed; visibility: hidden; width: 0; }} </style><!--[if mso]><xml> <o:OfficeDocumentSettings> <o:AllowPNG/> <o:PixelsPerInch>96</o:PixelsPerInch> </o:OfficeDocumentSettings> </xml><![endif]--><style type="text/css">a:link{{color: #666; text-decoration: underline;}}</style></head><body bgcolor="#ffffff" text="#414141" link="#666666" yahoo="fix" style="background-color: #ffffff;"> <table cellspacing="0" cellpadding="0" border="0" role="presentation" class="nl2go-body-table" width="100%" style="background-color: #ffffff; width: 100%;"><tbody><tr><td> <table cellspacing="0" cellpadding="0" border="0" role="presentation" width="100%" align="center" class="r0-o" style="table-layout: fixed; width: 100%;"><tbody><tr><td valign="top" class="r1-i" style="background-color: transparent;"> <table cellspacing="0" cellpadding="0" border="0" role="presentation" width="600" align="center" class="r0-o" style="table-layout: fixed;"><tbody><tr><td class="r3-i" style="padding-bottom: 5px; padding-top: 5px;"> <table width="100%" cellspacing="0" cellpadding="0" border="0" role="presentation"><tbody><tr><th width="100%" valign="top" class="r4-c" style="font-weight: normal;"> <table cellspacing="0" cellpadding="0" border="0" role="presentation" width="100%" align="center" class="r0-o" style="table-layout: fixed; width: 100%;"><tbody><tr><td align="center" class="r6-i nl2go-default-textstyle" style="color: #414141; font-family: Arial; font-size: 16px; line-height: 1.5; word-break: break-word; padding-left: 30px; padding-right: 30px; text-align: center;"> <div><p style="margin: 0;"><a href="" style="color: #666; text-decoration: underline;"> <span style="font-family: arial,helvetica,sans-serif; color: #858588; font-size: 12px; text-decoration: underline;"> View in browser</span></a></p></div> </td> </tr></tbody></table></th> </tr></tbody></table></td> </tr></tbody></table></td> </tr></tbody></table><table cellspacing="0" cellpadding="0" border="0" role="presentation" width="600" align="center" class="r0-o" style="table-layout: fixed; width: 600px;"><tbody><tr><td valign="top" class="r7-i" style="background-color: #ffffff;"> <table cellspacing="0" cellpadding="0" border="0" role="presentation" width="100%" align="center" class="r0-o" style="table-layout: fixed; width: 100%;"><tbody><tr><td class="r8-i" style="padding-bottom: 80px; padding-top: 20px;"> <table width="100%" cellspacing="0" cellpadding="0" border="0" role="presentation"><tbody><tr><th width="100%" valign="top" class="r4-c" style="font-weight: normal;"> <table cellspacing="0" cellpadding="0" border="0" role="presentation" width="100%" class="r5-o" style="table-layout: fixed; width: 100%;"><tbody><tr><td valign="top" class="r9-i" style="padding-left: 15px; padding-right: 15px;"> <table width="100%" cellspacing="0" cellpadding="0" border="0" role="presentation"><tbody><tr><td class="r2-c" align="center"> <table cellspacing="0" cellpadding="0" border="0" role="presentation" width="200" class="r0-o" style="table-layout: fixed; width: 200px;"><tbody><tr><td style="font-size: 0px; line-height: 0px;"> <img src="https://img-cache.net/im/10825850/61cea3da2bc77f202488ecb1720943d9d28b252ed603277bc179630e9dc745b9.png?e=sLtDvQnLQxWRLfup0OAOnegQ8cjLGjIbWQvB3ryxhmUDLw1zgoeGtjFoMWNpUen9YI6Fn6s3kv0ARmcqRHbFV0hNzQGlvYF4GBw7RZ2bcoCIJ9TpR98oPrTxx-80G7Ne-ycWA1kX0_xwwWLHo5tGSSy8DnnWsME1ciAxebGt_rXv-bkcuJWxfehjPzbvT4C_q31SdNxCMwV_WqWExKNHshuXyfWkJwOzm9mJP8Of0bJbvcEIZ3TB3Qk" width="200" border="0" style="display: block; width: 100%;" sib_link_id="0"/></td> </tr></tbody></table></td> </tr></tbody></table></td> </tr></tbody></table></th> </tr></tbody></table></td> </tr></tbody></table></td> </tr></tbody></table><table cellspacing="0" cellpadding="0" border="0" role="presentation" width="100%" align="center" class="r10-o" style="table-layout: fixed; width: 100%;"><tbody><tr><td valign="top" class="r11-i" style="background-color: #f5f5f5;"> <table cellspacing="0" cellpadding="0" border="0" role="presentation" width="600" align="center" class="r0-o" style="table-layout: fixed; width: 600px;"><tbody><tr><td class="r12-i" style="padding-bottom: 60px; padding-top: 60px;"> <table width="100%" cellspacing="0" cellpadding="0" border="0" role="presentation"><tbody><tr><th width="100%" valign="top" class="r4-c" style="font-weight: normal;"> <table cellspacing="0" cellpadding="0" border="0" role="presentation" width="100%" class="r5-o" style="table-layout: fixed; width: 100%;"><tbody><tr><td valign="top" class="r9-i"> <table width="100%" cellspacing="0" cellpadding="0" border="0" role="presentation"><tbody><tr><td class="r13-c nl2go-default-textstyle" align="center" style="color: #414141; font-family: Arial; font-size: 16px; word-break: break-word; line-height: 1; text-align: center; valign: top;"> <div><h1 class="default-heading1" style="margin: 0; color: #414141; font-family: Arial; font-size: 36px; font-weight: 400; word-break: break-word;"><span style="color: #222222;"><strong>Met het standaard trackingspakket van </strong></span></h1></div> </td> </tr><tr><td class="r14-c" align="left"> <table cellspacing="0" cellpadding="0" border="0" role="presentation" width="100%" class="r15-o" style="table-layout: fixed; width: 100%;"><tbody><tr><td align="center" valign="top" class="r16-i nl2go-default-textstyle" style="color: #414141; font-family: Arial; font-size: 16px; line-height: 1.5; word-break: break-word; padding-top: 8px; text-align: center;"> <div><p style="margin: 0;">Fleet Track Holland is het volgen van uw voertuigen </p><p style="margin: 0;">geen luxe meer,maar </p><p style="margin: 0;"><span style="font-size: 26px;">SUPEREENVOUDIG</span>.</p></div> </td> </tr></tbody></table></td> </tr><tr><td class="r17-c" align="center" style="align: center; padding-bottom: 0px; padding-top: 40px; valign: top;"> <table cellspacing="0" cellpadding="0" border="0" role="presentation" width="300" class="r18-o" style="background-color: #222222; border-collapse: separate; border-color: #666666; border-radius: 4px; border-style: solid; border-width: 0px; table-layout: fixed; width: 300px;"><tbody><tr><td height="18" align="center" valign="top" class="r19-i nl2go-default-textstyle" style="word-break: break-word; background-color: #222222; border-radius: 4px; color: #ffffff; font-family: Arial; font-size: 16px; font-style: normal; line-height: 1.15; padding-bottom: 12px; padding-top: 12px; text-align: center;"> <a href="{cta_url}" class="r20-r default-button" target="_blank" data-btn="1" style="font-style: normal; font-weight: normal; line-height: 1.15; text-decoration: none; word-break: break-word; word-wrap: break-word; display: block; -webkit-text-size-adjust: none; color: #ffffff; font-family: Arial; font-size: 16px;"> <span>Bekijk onze producten</span></a> </td> </tr></tbody></table></td> </tr></tbody></table></td> </tr></tbody></table></th> </tr></tbody></table></td> </tr></tbody></table></td> </tr></tbody></table><table cellspacing="0" cellpadding="0" border="0" role="presentation" width="600" align="center" class="r0-o" style="table-layout: fixed; width: 600px;"><tbody><tr><td valign="top" class="r7-i" style="background-color: #ffffff;"> <table cellspacing="0" cellpadding="0" border="0" role="presentation" width="100%" align="center" class="r0-o" style="table-layout: fixed; width: 100%;"><tbody><tr><td class="r21-i" style="padding-bottom: 20px; padding-top: 40px;"> <table width="100%" cellspacing="0" cellpadding="0" border="0" role="presentation"><tbody><tr><th width="100%" valign="top" class="r4-c" style="font-weight: normal;"> <table cellspacing="0" cellpadding="0" border="0" role="presentation" width="100%" align="left" class="r15-o" style="table-layout: fixed; width: 100%;"><tbody><tr><td align="left" valign="top" class="r22-i nl2go-default-textstyle" style="color: #414141; font-family: Arial; font-size: 16px; line-height: 1.5; word-break: break-word; text-align: left;"> <div><h2 class="default-heading2" style="margin: 0; color: #414141; font-family: Arial; font-size: 32px; font-weight: 400; word-break: break-word;"><strong>INSTALLATIE – GEBRUIK – BETALING</strong></h2></div> </td> </tr></tbody></table><table cellspacing="0" cellpadding="0" border="0" role="presentation" width="100%" align="left" class="r15-o" style="table-layout: fixed; width: 100%;"><tbody><tr><td align="left" valign="top" class="r23-i nl2go-default-textstyle" style="color: #414141; font-family: Arial; font-size: 16px; line-height: 1.5; word-break: break-word; padding-top: 5px; text-align: left;"> <div><p style="margin: 0;">Rapporteer in real time en achteraf de snelheid, route, locatie en gebruiksgegevens </p><p style="margin: 0;">van uw voertuigen in het veld!</p></div> </td> </tr></tbody></table></th> </tr></tbody></table></td> </tr></tbody></table><table cellspacing="0" cellpadding="0" border="0" role="presentation" width="100%" align="center" class="r0-o" style="table-layout: fixed; width: 100%;"><tbody><tr><td class="r24-i" style="padding-bottom: 40px; padding-top: 20px;"> <table width="100%" cellspacing="0" cellpadding="0" border="0" role="presentation"><tbody><tr><th width="33.33%" valign="top" class="r4-c" style="font-weight: normal;"> <table cellspacing="0" cellpadding="0" border="0" role="presentation" width="100%" class="r5-o" style="table-layout: fixed; width: 100%;"><tbody><tr><td valign="top" class="r25-i" style="padding-left: 15px; padding-right: 15px;"> <table width="100%" cellspacing="0" cellpadding="0" border="0" role="presentation"><tbody><tr><td class="r2-c" align="center" style="border-radius: 8px; font-size: 0px; line-height: 0px; valign: top;"> <img src="https://img-cache.net/im/10825850/56dac7201eea0c071394114e9ddf957f8344310239f78b01ba068f84d00e9d0b.png?e=4vsQN4oAZ2slm-aU6oxDa6l56CIeT_8cVDVQMIfTuGhEHNIaJH01Fu-Ri7asOZUJJ-WHjlT4_Sd33zzkLPIGH5S8Bn0fIyi2p7nyxZLRcZ1gdnOuZpruMwSv_41tF0WrHISiPGDCqgq_o5Eh7ke_uCdIouakafUjBzmlZJ3dzlMdMPbeGDgyRluSctCDP75h-r8yBrPFx6ae49-dxhy6nJUEcOmEcX4eyhcYdyGNj6hsW5Lf_846EHg" width="169" border="0" style="display: block; width: 100%; border-radius: 8px;" sib_link_id="1"/></td> </tr><tr><td class="r26-c nl2go-default-textstyle" align="left" style="color: #414141; font-family: Arial; font-size: 16px; line-height: 1.5; word-break: break-word; padding-top: 10px; text-align: left; valign: top;"> <div><p style="margin: 0;">FTC961</p></div> </td> </tr><tr><td class="r27-c nl2go-default-textstyle" align="left" style="color: #414141; font-family: Arial; font-size: 16px; line-height: 1.5; word-break: break-word; padding-top: 5px; text-align: left; valign: top;"> <div><p style="margin: 0;">Al onze producten zijn water- en stofdicht.</p></div> </td> </tr><tr><td class="r17-c" align="center" style="align: center; padding-bottom: 0px; padding-top: 15px; valign: top;"> <table cellspacing="0" cellpadding="0" border="0" role="presentation" width="169" class="r28-o" style="background-color: #222222; border-collapse: separate; border-color: #666666; border-radius: 4px; border-style: solid; border-width: 0px; table-layout: fixed; width: 169px;"><tbody><tr><td height="18" align="center" valign="top" class="r19-i nl2go-default-textstyle" style="word-break: break-word; background-color: #222222; border-radius: 4px; color: #ffffff; font-family: Arial; font-size: 16px; font-style: normal; line-height: 1.15; padding-bottom: 12px; padding-top: 12px; text-align: center;"> <a href="{cta_url}" class="r20-r default-button" target="_blank" data-btn="2" style="font-style: normal; font-weight: normal; line-height: 1.15; text-decoration: none; word-break: break-word; word-wrap: break-word; display: block; -webkit-text-size-adjust: none; color: #ffffff; font-family: Arial; font-size: 16px;"> <span>Nu winkelen</span></a> </td> </tr></tbody></table></td> </tr></tbody></table></td> </tr></tbody></table></th> <th width="33.33%" valign="top" class="r4-c" style="font-weight: normal;"> <table cellspacing="0" cellpadding="0" border="0" role="presentation" width="100%" class="r5-o" style="table-layout: fixed; width: 100%;"><tbody><tr><td valign="top" class="r25-i" style="padding-left: 15px; padding-right: 15px;"> <table width="100%" cellspacing="0" cellpadding="0" border="0" role="presentation"><tbody><tr><td class="r2-c" align="center" style="border-radius: 8px; font-size: 0px; line-height: 0px; valign: top;"> <img src="https://img-cache.net/im/10825850/705488db95bbdf389d1cf71cd369e658f4551866e843e0423fb10d0318a5b20b.png?e=pzKSdZr40x3qrqzur5N6QNp9IMVlI4aMoVJ_KyM4wwgfPsRf97UuOgnkPjM2CjU-rfm88_aro80nN9RIaTpS_JNh_PyvYP-ITRhXtatSJptYX_dDmlP1RixGigCjU-vJ4osbpl5LiKsd2t8gqaCHpvhtbngul-ceALwbYERBkdgSGqY6EiOa7IK0sJzjecHTPUZ8rFru8Tjb7j24XhhPns5ddGl0139MrkcRsUtMF4ZSqWzHda7atPs" width="169" border="0" style="display: block; width: 100%; border-radius: 8px;" sib_link_id="2"/></td> </tr><tr><td class="r26-c nl2go-default-textstyle" align="left" style="color: #414141; font-family: Arial; font-size: 16px; line-height: 1.5; word-break: break-word; padding-top: 10px; text-align: left; valign: top;"> <div><p style="margin: 0;">DashCam</p></div> </td> </tr><tr><td class="r27-c nl2go-default-textstyle" align="left" style="color: #414141; font-family: Arial; font-size: 16px; line-height: 1.5; word-break: break-word; padding-top: 5px; text-align: left; valign: top;"> <div><p style="margin: 0;">Onze camera&#39;s voor binnen, buiten en als combinatie van beide.</p></div> </td> </tr><tr><td class="r17-c" align="center" style="align: center; padding-bottom: 0px; padding-top: 15px; valign: top;"> <table cellspacing="0" cellpadding="0" border="0" role="presentation" width="169" class="r28-o" style="background-color: #222222; border-collapse: separate; border-color: #666666; border-radius: 4px; border-style: solid; border-width: 0px; table-layout: fixed; width: 169px;"><tbody><tr><td height="18" align="center" valign="top" class="r19-i nl2go-default-textstyle" style="word-break: break-word; background-color: #222222; border-radius: 4px; color: #ffffff; font-family: Arial; font-size: 16px; font-style: normal; line-height: 1.15; padding-bottom: 12px; padding-top: 12px; text-align: center;"> <a href="{cta_url}" class="r20-r default-button" target="_blank" data-btn="3" style="font-style: normal; font-weight: normal; line-height: 1.15; text-decoration: none; word-break: break-word; word-wrap: break-word; display: block; -webkit-text-size-adjust: none; color: #ffffff; font-family: Arial; font-size: 16px;"> <span>Nu winkelen</span></a> </td> </tr></tbody></table></td> </tr></tbody></table></td> </tr></tbody></table></th> <th width="33.33%" valign="top" class="r4-c" style="font-weight: normal;"> <table cellspacing="0" cellpadding="0" border="0" role="presentation" width="100%" class="r5-o" style="table-layout: fixed; width: 100%;"><tbody><tr><td valign="top" class="r25-i" style="padding-left: 15px; padding-right: 15px;"> <table width="100%" cellspacing="0" cellpadding="0" border="0" role="presentation"><tbody><tr><td class="r2-c" align="center" style="border-radius: 8px; font-size: 0px; line-height: 0px; valign: top;"> <img src="https://img-cache.net/im/10825850/7065a8fc5e4a949ad8b73edf0e0ce2b92c9073a9f6c46606a24df90962fb000b.png?e=MqPQGdpvErcC5B2ytYR6DytOe3s5T_abkDdBjlqZBjl4vO503-FWosvT_4GGJ8LFLEGxb7zp5O2NJOxFHQv6qpp1qDJakhBUL-KfO7V_YDSJl4U8y5W8wkDbol5KkiY7meLBGIJWT3Z7XoWmFutbkKQnp-oVdYCASvxYmmbphwR_DfHdYtS90Dzc74PhhEXyoRb8zoAJuBOu4fW28ER8SU_BwY3rWLC-YRE0a1ILjxmGUG3yH4f8xdM" width="169" border="0" style="display: block; width: 100%; border-radius: 8px;" sib_link_id="3"/></td> </tr><tr><td class="r26-c nl2go-default-textstyle" align="left" style="color: #414141; font-family: Arial; font-size: 16px; line-height: 1.5; word-break: break-word; padding-top: 10px; text-align: left; valign: top;"> <div><p style="margin: 0;">Best Sellers</p></div> </td> </tr><tr><td class="r27-c nl2go-default-textstyle" align="left" style="color: #414141; font-family: Arial; font-size: 16px; line-height: 1.5; word-break: break-word; padding-top: 5px; text-align: left; valign: top;"> <div><p style="margin: 0;">Onze bestverkochte producten aller tijden</p></div> </td> </tr><tr><td class="r17-c" align="center" style="align: center; padding-bottom: 0px; padding-top: 15px; valign: top;"> <table cellspacing="0" cellpadding="0" border="0" role="presentation" width="169" class="r28-o" style="background-color: #222222; border-collapse: separate; border-color: #666666; border-radius: 4px; border-style: solid; border-width: 0px; table-layout: fixed; width: 169px;"><tbody><tr><td height="18" align="center" valign="top" class="r19-i nl2go-default-textstyle" style="word-break: break-word; background-color: #222222; border-radius: 4px; color: #ffffff; font-family: Arial; font-size: 16px; font-style: normal; line-height: 1.15; padding-bottom: 12px; padding-top: 12px; text-align: center;"> <a href="{cta_url}" class="r20-r default-button" target="_blank" data-btn="4" style="font-style: normal; font-weight: normal; line-height: 1.15; text-decoration: none; word-break: break-word; word-wrap: break-word; display: block; -webkit-text-size-adjust: none; color: #ffffff; font-family: Arial; font-size: 16px;"> <span>Nu winkelen</span></a> </td> </tr></tbody></table></td> </tr></tbody></table></td> </tr></tbody></table></th> </tr></tbody></table></td> </tr></tbody></table><table cellspacing="0" cellpadding="0" border="0" role="presentation" width="100%" align="center" class="r10-o" style="table-layout: fixed; width: 100%;"><tbody><tr><td class="r29-i" style="background-color: #f5f5f5; padding-bottom: 40px; padding-left: 15px; padding-right: 15px; padding-top: 40px;"> <table width="100%" cellspacing="0" cellpadding="0" border="0" role="presentation"><tbody><tr><th width="100%" valign="top" class="r4-c" style="font-weight: normal;"> <table cellspacing="0" cellpadding="0" border="0" role="presentation" width="100%" align="left" class="r15-o" style="table-layout: fixed; width: 100%;"><tbody><tr><td align="center" valign="top" class="r30-i nl2go-default-textstyle" style="color: #414141; font-family: Arial; font-size: 16px; line-height: 1.5; word-break: break-word; text-align: center;"> <div><p style="margin: 0;">Mis onze lopende actie op een specifieke selectie producten niet, geldig voor een beperkte periode met deze kortingsbon:</p></div> </td> </tr></tbody></table><table cellspacing="0" cellpadding="0" border="0" role="presentation" width="100%" align="left" class="r15-o" style="table-layout: fixed; width: 100%;"><tbody><tr><td align="center" valign="top" class="r31-i nl2go-default-textstyle" style="color: #414141; font-family: Arial; font-size: 16px; line-height: 1.5; word-break: break-word; padding-bottom: 20px; padding-top: 20px; text-align: center;"> <div><h1 class="default-heading1" style="margin: 0; color: #414141; font-family: Arial; font-size: 36px; font-weight: 400; word-break: break-word;"><span style="color: #414141;"><strong>PROMO26</strong></span></h1></div> </td> </tr></tbody></table></th> </tr></tbody></table></td> </tr></tbody></table><table cellspacing="0" cellpadding="0" border="0" role="presentation" width="100%" align="center" class="r0-o" style="table-layout: fixed; width: 100%;"><tbody><tr><td class="r32-i" style="padding-bottom: 20px; padding-top: 80px;"> <table width="100%" cellspacing="0" cellpadding="0" border="0" role="presentation"><tbody><tr><th width="100%" valign="top" class="r4-c" style="font-weight: normal;"> <table cellspacing="0" cellpadding="0" border="0" role="presentation" width="100%" class="r5-o" style="table-layout: fixed; width: 100%;"><tbody><tr><td valign="top" class="r9-i" style="padding-left: 15px; padding-right: 15px;"> <table width="100%" cellspacing="0" cellpadding="0" border="0" role="presentation"><tbody><tr><td class="r14-c" align="left"> <table cellspacing="0" cellpadding="0" border="0" role="presentation" width="114" class="r15-o" style="table-layout: fixed; width: 114px;"><tbody><tr><td class="r33-i" style="font-size: 0px; line-height: 0px; padding-bottom: 10px;"> <img src="https://img-cache.net/im/10825850/61cea3da2bc77f202488ecb1720943d9d28b252ed603277bc179630e9dc745b9.png?e=UzOjypCjzylBEWYeEbEN13ZMMkvaQCaXL-b1D0m1emya7Faqmng-HCrjpJxVjRgKruSTAdNaI3_n7G_sslNWZo9UxZmecRBkuETaZEVcLWb8Rgo3wZt2kRfPHI6U4GHSiKUOWViCl5ePIC_0pwYBigWm3SY8p2IMjEM0atV9Tpw7clym0xd4bujmMgq95rAuKGsKiJVQELaubzi2HDtuLo3lOjLlBmjjuKaalNVt51CjzeRHxzX56ZU" width="114" border="0" style="display: block; width: 100%;" sib_link_id="0"/></td> </tr></tbody></table></td> </tr><tr><td class="r34-c nl2go-default-textstyle" align="left" style="color: #414141; font-family: Arial; font-size: 16px; line-height: 1.5; word-break: break-word; padding-bottom: 10px; text-align: left; valign: top;"> <div><p style="margin: 0; color: #000000; font-size: 14px;"><strong>Fleet Track Holland</strong></p></div> </td> </tr><tr><td class="r34-c nl2go-default-textstyle" align="left" style="color: #414141; font-family: Arial; font-size: 16px; line-height: 1.5; word-break: break-word; padding-bottom: 10px; text-align: left; valign: top;"> <div><p style="margin: 0;"><span style="color: #666666; font-size: 14px;">Rotterdam</span></p></div> </td> </tr><tr><td class="r35-c nl2go-default-textstyle" align="left" style="color: #414141; font-family: Arial; font-size: 16px; line-height: 1.5; word-break: break-word; padding-top: 10px; text-align: left; valign: top;"> <div><p style="margin: 0;"><span style="color: #666666; font-size: 14px;">Deze e-mail werd verzonden naar</span><span style="color: #666666; font-size: 14px;"> info@fleettrackholland.nl.</span></p><p style="margin: 0;"><span style="color: #666666; font-size: 14px;">U hebt deze e-mail ontvangen omdat u zich hebt aangemeld voor onze nieuwsbrief.</span></p></div> </td> </tr><tr><td class="r35-c nl2go-default-textstyle" align="left" style="color: #414141; font-family: Arial; font-size: 16px; line-height: 1.5; word-break: break-word; padding-top: 10px; text-align: left; valign: top;"> <div><p style="margin: 0;"><a href="{unsubscribe_url}" target="_blank" style="color: #666; text-decoration: underline;"><span style="color: #666666; font-size: 14px;"><u>Unsubscribe</u></span></a></p></div> </td> </tr></tbody></table></td> </tr></tbody></table></th> </tr></tbody></table></td> </tr></tbody></table></td> </tr></tbody></table></td> </tr></tbody></table>
<div style="color: #727272; font-size: 10px;"><center></center></div></body></html>""",
    },

    # ═══════════════════════════════════════════════════════════════
    # 1. FLEET CORPORATE — Ferrari kırmızı + koyu gri, 3 ürün
    # ═══════════════════════════════════════════════════════════════
    "fleet_corporate": {
        "name": "Fleet Corporate",
        "description": "Kurumsal — Ferrari kırmızı + koyu gri, 3 ürün görseli",
        "sectors": ["corporate"],
        "html": _HEAD + """
<body style="margin:0;padding:0;background-color:#f0f2f5;font-family:'Segoe UI',Roboto,Arial,Helvetica,sans-serif;-webkit-font-smoothing:antialiased;">

<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#f0f2f5;">
<tr><td align="center" style="padding:24px 12px;">

<table role="presentation" width="620" cellpadding="0" cellspacing="0" border="0" style="max-width:620px;width:100%;background-color:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.08);">

  <!-- Header logo on dark charcoal -->
  <tr><td style="padding:20px 32px;background:linear-gradient(135deg,#1c1c1c,#2d2d2d);border-bottom:3px solid #CC0000;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
    <tr>
      <td><img src="{logo_url}" alt="FleetTrack Holland" style="height:32px;width:auto;display:block;" /></td>
      <td align="right" style="font-size:12px;color:#CC0000;font-weight:600;">GPS Tracking &amp; Vlootbeheer</td>
    </tr>
    </table>
  </td></tr>

  <!-- Ferrari red gradient hero -->
  <tr><td style="background:linear-gradient(135deg,#CC0000,#e8600a,#CC0000);padding:36px 32px;text-align:center;">
    <p style="margin:0 0 8px;font-size:12px;color:rgba(255,255,255,0.85);text-transform:uppercase;letter-spacing:2px;font-weight:600;">PROFESSIONAL FLEET MANAGEMENT</p>
    <p style="margin:0;font-size:24px;font-weight:700;color:#ffffff;line-height:1.3;">{headline}</p>
  </td></tr>

""" + _PRODUCTS_3_GREY + """

  <!-- Body content -->
  <tr><td style="padding:32px 32px 24px;background-color:#ffffff;">
    {body_content}
  </td></tr>

  <!-- CTA section -->
  <tr><td style="padding:28px 32px;background-color:#f5f0f0;border-top:1px solid #e8d8d8;border-bottom:1px solid #e8d8d8;text-align:center;">
    <p style="margin:0 0 16px;font-size:16px;font-weight:600;color:#1c1c1c;">Ontdek wat FleetTrack voor u kan betekenen</p>
    <a href="{cta_url}" style="display:inline-block;padding:14px 40px;background-color:#CC0000;color:#ffffff;text-decoration:none;border-radius:6px;font-weight:bold;font-size:15px;letter-spacing:0.3px;">{cta_text}</a>
  </td></tr>

  <!-- Trust stats bar -->
  <tr><td style="padding:20px 32px;background-color:#f8f9fb;text-align:center;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
    <tr>
      <td align="center" style="padding:0 8px;">
        <p style="margin:0;font-size:20px;font-weight:700;color:#CC0000;">300+</p>
        <p style="margin:2px 0 0;font-size:11px;color:#777;">Klanten</p>
      </td>
      <td align="center" style="padding:0 8px;">
        <p style="margin:0;font-size:20px;font-weight:700;color:#CC0000;">25%</p>
        <p style="margin:2px 0 0;font-size:11px;color:#777;">Kostenbesparing</p>
      </td>
      <td align="center" style="padding:0 8px;">
        <p style="margin:0;font-size:20px;font-weight:700;color:#CC0000;">24/7</p>
        <p style="margin:2px 0 0;font-size:11px;color:#777;">Live Tracking</p>
      </td>
      <td align="center" style="padding:0 8px;">
        <p style="margin:0;font-size:20px;font-weight:700;color:#CC0000;">€9,95</p>
        <p style="margin:2px 0 0;font-size:11px;color:#777;">/mnd all-in</p>
      </td>
    </tr>
    </table>
  </td></tr>

  <!-- Footer -->
  <tr><td style="padding:20px 32px;background-color:#1c1c1c;text-align:center;">
    <p style="margin:0;font-size:12px;color:#a0a0a0;">FleetTrack Holland B.V. | sales@fleettrackholland.nl</p>
    <p style="margin:8px 0 0;font-size:11px;color:#666;">
      <a href="{unsubscribe_url}" style="color:#888;text-decoration:underline;">Uitschrijven</a>
      &nbsp;|&nbsp;
      <a href="https://www.fleettrackholland.nl/privacy" style="color:#888;text-decoration:underline;">Privacybeleid</a>
    </p>
  </td></tr>

""" + _TAIL,
    },

    # ═══════════════════════════════════════════════════════════════
    # 2. FLEET TRANSPORT — Mavi, 2 ürün (KULLANICI BEĞENDİ ✓)
    # ═══════════════════════════════════════════════════════════════
    "fleet_transport": {
        "name": "Fleet Transport",
        "description": "Transport/logistiek — mavi tonlar, 2 ürün görseli",
        "sectors": ["transport", "logistiek", "koerier"],
        "html": _HEAD + """
<body style="margin:0;padding:0;background-color:#eef2f7;font-family:'Segoe UI',Roboto,Arial,Helvetica,sans-serif;-webkit-font-smoothing:antialiased;">

<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#eef2f7;">
<tr><td align="center" style="padding:24px 12px;">

<table role="presentation" width="620" cellpadding="0" cellspacing="0" border="0" style="max-width:620px;width:100%;background-color:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.08);">

  <!-- Dark header with logo + tagline -->
  <tr><td style="padding:24px 32px;background:linear-gradient(135deg,#0f2847,#1a3f6f);">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
    <tr>
      <td><img src="{logo_url}" alt="FleetTrack Holland" style="height:32px;width:auto;display:block;" /></td>
      <td align="right" style="font-size:12px;color:#7aa3d4;">Transportoplossingen</td>
    </tr>
    </table>
  </td></tr>

  <!-- Hero banner -->
  <tr><td style="padding:0;">
    <div style="background:linear-gradient(135deg,#0f2847 0%,#1a5fa0 50%,#2980b9 100%);padding:40px 32px;text-align:center;">
      <p style="margin:0 0 8px;font-size:13px;color:#7ab8e0;text-transform:uppercase;letter-spacing:2px;font-weight:600;">GPS Fleet Tracking</p>
      <p style="margin:0;font-size:24px;font-weight:700;color:#ffffff;line-height:1.3;">{headline}</p>
    </div>
  </td></tr>

""" + _PRODUCTS_2_WHITE + """

  <!-- Body content -->
  <tr><td style="padding:32px 32px 24px;background-color:#ffffff;">
    {body_content}
  </td></tr>

  <!-- Stats section -->
  <tr><td style="padding:24px 32px;background-color:#f0f6fc;border-top:1px solid #d6e4f0;border-bottom:1px solid #d6e4f0;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
    <tr>
      <td align="center" width="33%" style="padding:8px;">
        <p style="margin:0;font-size:28px;font-weight:700;color:#1a5fa0;">23%</p>
        <p style="margin:4px 0 0;font-size:11px;color:#666;">Brandstofbesparing</p>
      </td>
      <td align="center" width="33%" style="padding:8px;">
        <p style="margin:0;font-size:28px;font-weight:700;color:#1a5fa0;">40%</p>
        <p style="margin:4px 0 0;font-size:11px;color:#666;">Efficiëntiewinst</p>
      </td>
      <td align="center" width="33%" style="padding:8px;">
        <p style="margin:0;font-size:28px;font-weight:700;color:#1a5fa0;">€9,95</p>
        <p style="margin:4px 0 0;font-size:11px;color:#666;">/mnd per voertuig</p>
      </td>
    </tr>
    </table>
  </td></tr>

  <!-- CTA -->
  <tr><td style="padding:28px 32px;background-color:#ffffff;text-align:center;">
    <a href="{cta_url}" style="display:inline-block;padding:14px 40px;background:linear-gradient(135deg,#1a5fa0,#2980b9);color:#ffffff;text-decoration:none;border-radius:6px;font-weight:bold;font-size:15px;">{cta_text}</a>
  </td></tr>

  <!-- Footer -->
  <tr><td style="padding:20px 32px;background-color:#0f2847;text-align:center;">
    <p style="margin:0;font-size:12px;color:#7aa3d4;">FleetTrack Holland B.V. | sales@fleettrackholland.nl</p>
    <p style="margin:8px 0 0;font-size:11px;">
      <a href="{unsubscribe_url}" style="color:#5a8ab5;text-decoration:underline;">Uitschrijven</a>
      &nbsp;|&nbsp;
      <a href="https://www.fleettrackholland.nl/privacy" style="color:#5a8ab5;text-decoration:underline;">Privacybeleid</a>
    </p>
  </td></tr>

""" + _TAIL,
    },

    # ═══════════════════════════════════════════════════════════════
    # 3. FLEET SECURITY — Ferrari kırmızı, 2 ürün (güvenlik odaklı)
    # ═══════════════════════════════════════════════════════════════
    "fleet_security": {
        "name": "Fleet Security",
        "description": "Bouw/beveiliging — Ferrari kırmızı, 2 güvenlik ürünü",
        "sectors": ["bouw", "beveiliging"],
        "html": _HEAD + """
<body style="margin:0;padding:0;background-color:#f5f0ee;font-family:'Segoe UI',Roboto,Arial,Helvetica,sans-serif;-webkit-font-smoothing:antialiased;">

<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#f5f0ee;">
<tr><td align="center" style="padding:24px 12px;">

<table role="presentation" width="620" cellpadding="0" cellspacing="0" border="0" style="max-width:620px;width:100%;background-color:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.08);">

  <!-- Header on dark charcoal -->
  <tr><td style="padding:20px 32px;background:linear-gradient(135deg,#1c1c1c,#333333);border-bottom:3px solid #CC0000;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
    <tr>
      <td><img src="{logo_url}" alt="FleetTrack Holland" style="height:32px;width:auto;display:block;" /></td>
      <td align="right" style="font-size:12px;color:#CC0000;font-weight:600;">Voertuigbeveiliging</td>
    </tr>
    </table>
  </td></tr>

  <!-- Ferrari red alert hero -->
  <tr><td style="background:linear-gradient(135deg,#CC0000,#e8600a,#CC0000);padding:36px 32px;text-align:center;">
    <p style="margin:0 0 8px;font-size:12px;color:rgba(255,255,255,0.85);text-transform:uppercase;letter-spacing:2px;font-weight:700;">⚠ BEVEILIGINGSADVIES</p>
    <p style="margin:0;font-size:22px;font-weight:700;color:#ffffff;line-height:1.3;">{headline}</p>
  </td></tr>

  <!-- Warning stats -->
  <tr><td style="padding:24px 32px;background-color:#f5f0f0;border-bottom:1px solid #e0d0d0;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
    <tr>
      <td align="center" width="33%" style="padding:8px;">
        <p style="margin:0;font-size:28px;font-weight:700;color:#CC0000;">+23%</p>
        <p style="margin:4px 0 0;font-size:11px;color:#888;">Meer diefstal in 2024</p>
      </td>
      <td align="center" width="33%" style="padding:8px;">
        <p style="margin:0;font-size:28px;font-weight:700;color:#CC0000;">€45K</p>
        <p style="margin:4px 0 0;font-size:11px;color:#888;">Gem. schadebedrag</p>
      </td>
      <td align="center" width="33%" style="padding:8px;">
        <p style="margin:0;font-size:28px;font-weight:700;color:#22a85a;">92%</p>
        <p style="margin:4px 0 0;font-size:11px;color:#888;">Terugvindingsratio</p>
      </td>
    </tr>
    </table>
  </td></tr>

  <!-- Body content -->
  <tr><td style="padding:32px 32px 24px;background-color:#ffffff;">
    {body_content}
  </td></tr>

""" + _PRODUCT_SECURITY + """

  <!-- CTA -->
  <tr><td style="padding:24px 32px;background-color:#ffffff;text-align:center;">
    <a href="{cta_url}" style="display:inline-block;padding:14px 40px;background:linear-gradient(135deg,#CC0000,#e8600a);color:#ffffff;text-decoration:none;border-radius:6px;font-weight:bold;font-size:15px;">{cta_text}</a>
  </td></tr>

  <!-- Footer -->
  <tr><td style="padding:20px 32px;background-color:#1c1c1c;text-align:center;">
    <p style="margin:0;font-size:12px;color:#a0a0a0;">FleetTrack Holland B.V. | sales@fleettrackholland.nl</p>
    <p style="margin:8px 0 0;font-size:11px;">
      <a href="{unsubscribe_url}" style="color:#888;text-decoration:underline;">Uitschrijven</a>
      &nbsp;|&nbsp;
      <a href="https://www.fleettrackholland.nl/privacy" style="color:#888;text-decoration:underline;">Privacybeleid</a>
    </p>
  </td></tr>

""" + _TAIL,
    },

    # ═══════════════════════════════════════════════════════════════
    # 4. FLEET SAVINGS — Yeşil, 3 ürün (KULLANICI BEĞENDİ ✓)
    # ═══════════════════════════════════════════════════════════════
    "fleet_savings": {
        "name": "Fleet Savings",
        "description": "ROI & kostenbesparing — yeşil accent, 3 ürün görseli",
        "sectors": ["schoonmaak", "thuiszorg", "catering"],
        "html": _HEAD + """
<body style="margin:0;padding:0;background-color:#f0f5f0;font-family:'Segoe UI',Roboto,Arial,Helvetica,sans-serif;-webkit-font-smoothing:antialiased;">

<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#f0f5f0;">
<tr><td align="center" style="padding:24px 12px;">

<table role="presentation" width="620" cellpadding="0" cellspacing="0" border="0" style="max-width:620px;width:100%;background-color:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.08);">

  <!-- Green accent bar -->
  <tr><td style="height:5px;background:linear-gradient(90deg,#22a85a,#34d399,#22a85a);font-size:0;line-height:0;">&nbsp;</td></tr>

  <!-- Header -->
  <tr><td style="padding:24px 32px 16px;background-color:#ffffff;border-bottom:1px solid #e8f0e8;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
    <tr>
      <td><img src="{logo_url}" alt="FleetTrack Holland" style="height:32px;width:auto;display:block;" /></td>
      <td align="right" style="font-size:12px;color:#22a85a;font-weight:600;">Kostenbesparing</td>
    </tr>
    </table>
  </td></tr>

  <!-- Savings hero -->
  <tr><td style="padding:32px;background:linear-gradient(135deg,#f0faf4,#ffffff);text-align:center;border-bottom:1px solid #e0f0e0;">
    <p style="margin:0 0 4px;font-size:12px;color:#22a85a;text-transform:uppercase;letter-spacing:2px;font-weight:600;">Uw potentiële besparing</p>
    <p style="margin:0;font-size:44px;font-weight:800;color:#22a85a;line-height:1.1;">{headline}</p>
    <p style="margin:8px 0 0;font-size:14px;color:#666;">per maand met FleetTrack GPS tracking</p>
  </td></tr>

  <!-- Body content -->
  <tr><td style="padding:32px 32px 24px;background-color:#ffffff;">
    {body_content}
  </td></tr>

  <!-- Benefits grid -->
  <tr><td style="padding:24px 32px;background-color:#f7faf7;border-top:1px solid #e0f0e0;border-bottom:1px solid #e0f0e0;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
    <tr>
      <td width="50%" style="padding:8px 8px 8px 0;">
        <div style="padding:16px;background:#ffffff;border-radius:8px;border:1px solid #e0f0e0;">
          <p style="margin:0;font-size:11px;color:#888;text-transform:uppercase;">Brandstof</p>
          <p style="margin:4px 0 0;font-size:20px;font-weight:700;color:#22a85a;">-25%</p>
        </div>
      </td>
      <td width="50%" style="padding:8px 0 8px 8px;">
        <div style="padding:16px;background:#ffffff;border-radius:8px;border:1px solid #e0f0e0;">
          <p style="margin:0;font-size:11px;color:#888;text-transform:uppercase;">Administratie</p>
          <p style="margin:4px 0 0;font-size:20px;font-weight:700;color:#22a85a;">-40%</p>
        </div>
      </td>
    </tr>
    <tr>
      <td width="50%" style="padding:8px 8px 8px 0;">
        <div style="padding:16px;background:#ffffff;border-radius:8px;border:1px solid #e0f0e0;">
          <p style="margin:0;font-size:11px;color:#888;text-transform:uppercase;">Privégebruik</p>
          <p style="margin:4px 0 0;font-size:20px;font-weight:700;color:#22a85a;">-62%</p>
        </div>
      </td>
      <td width="50%" style="padding:8px 0 8px 8px;">
        <div style="padding:16px;background:#ffffff;border-radius:8px;border:1px solid #e0f0e0;">
          <p style="margin:0;font-size:11px;color:#888;text-transform:uppercase;">ROI</p>
          <p style="margin:4px 0 0;font-size:20px;font-weight:700;color:#22a85a;">&lt;3 mnd</p>
        </div>
      </td>
    </tr>
    </table>
  </td></tr>

""" + _PRODUCTS_3_GREY + """

  <!-- CTA -->
  <tr><td style="padding:28px 32px;background-color:#ffffff;text-align:center;">
    <a href="{cta_url}" style="display:inline-block;padding:14px 40px;background:linear-gradient(135deg,#22a85a,#34d399);color:#ffffff;text-decoration:none;border-radius:6px;font-weight:bold;font-size:15px;">{cta_text}</a>
  </td></tr>

  <!-- Footer -->
  <tr><td style="padding:20px 32px;background-color:#1a2e1a;text-align:center;">
    <p style="margin:0;font-size:12px;color:#7aaa7a;">FleetTrack Holland B.V. | sales@fleettrackholland.nl</p>
    <p style="margin:8px 0 0;font-size:11px;">
      <a href="{unsubscribe_url}" style="color:#5a8a5a;text-decoration:underline;">Uitschrijven</a>
      &nbsp;|&nbsp;
      <a href="https://www.fleettrackholland.nl/privacy" style="color:#5a8a5a;text-decoration:underline;">Privacybeleid</a>
    </p>
  </td></tr>

""" + _TAIL,
    },

    # ═══════════════════════════════════════════════════════════════
    # 5. FLEET MINIMAL — Follow-up, inline ürün satırı
    # ═══════════════════════════════════════════════════════════════
    "fleet_minimal": {
        "name": "Fleet Minimal",
        "description": "Follow-up — temiz, inline ürün + CTA",
        "sectors": ["followup"],
        "html": _HEAD + """
<body style="margin:0;padding:0;background-color:#f5f5f5;font-family:'Segoe UI',Roboto,Arial,Helvetica,sans-serif;-webkit-font-smoothing:antialiased;">

<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#f5f5f5;">
<tr><td align="center" style="padding:24px 12px;">

<table role="presentation" width="620" cellpadding="0" cellspacing="0" border="0" style="max-width:620px;width:100%;background-color:#ffffff;border-radius:8px;overflow:hidden;box-shadow:0 2px 16px rgba(0,0,0,0.06);">

  <!-- Red accent bar -->
  <tr><td style="height:4px;background:linear-gradient(90deg,#CC0000,#e8600a,#CC0000);font-size:0;line-height:0;">&nbsp;</td></tr>

  <!-- Compact header -->
  <tr><td style="padding:20px 32px;border-bottom:1px solid #f0f0f0;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
    <tr>
      <td><img src="{logo_url}" alt="FleetTrack Holland" style="height:28px;width:auto;display:block;" /></td>
      <td align="right" style="font-size:11px;color:#999;">Follow-up</td>
    </tr>
    </table>
  </td></tr>

  <!-- Body content -->
  <tr><td style="padding:28px 32px;background-color:#ffffff;">
    {body_content}
  </td></tr>

""" + _PRODUCT_INLINE + """

  <!-- Minimal footer -->
  <tr><td style="padding:16px 32px;background-color:#fafafa;text-align:center;">
    <p style="margin:0;font-size:11px;color:#999;">
      FleetTrack Holland B.V. | sales@fleettrackholland.nl
      &nbsp;|&nbsp;
      <a href="{unsubscribe_url}" style="color:#999;text-decoration:underline;">Uitschrijven</a>
    </p>
  </td></tr>

""" + _TAIL,
    },
}

# ─── SECTOR → TEMPLATE MAPPING ─────────────────────────────────
SECTOR_TEMPLATE_MAP = {
    "transport": "fleet_transport",
    "logistiek": "fleet_transport",
    "koerier": "fleet_transport",
    "bouw": "fleet_security",
    "beveiliging": "fleet_security",
    "schoonmaak": "fleet_savings",
    "thuiszorg": "fleet_savings",
    "catering": "fleet_savings",
}

# Varsayılan CTA
DEFAULT_CTA_URL = "https://www.fleettrackholland.nl/prijzen"
DEFAULT_CTA_TEXT = "Bekijk tarieven →"
DEFAULT_UNSUB_URL = "https://www.fleettrackholland.nl/unsubscribe"


class TemplateEngine:
    """Email şablon motoru v3 — Çoklu ürün görseli, profesyonel newsletter."""

    def __init__(self):
        self._active_template = "brevo_official"
        log.info(f"TemplateEngine v4 hazır ({len(TEMPLATES)} şablon — varsayılan: Brevo Official).")

    def get_templates(self) -> list[dict]:
        """Mevcut şablonları listele."""
        return [
            {
                "id": tid,
                "name": t["name"],
                "description": t["description"],
                "sectors": t["sectors"],
                "active": tid == self._active_template,
            }
            for tid, t in TEMPLATES.items()
        ]

    def set_active(self, template_id: str) -> bool:
        """Aktif şablonu değiştir."""
        if template_id in TEMPLATES:
            self._active_template = template_id
            log.info(f"[TEMPLATE] Aktif şablon: {template_id}")
            return True
        return False

    def get_best_template(self, sector: str = "") -> str:
        """Sektöre göre en uygun şablonu seç."""
        sector_lower = (sector or "").lower().strip()
        return SECTOR_TEMPLATE_MAP.get(sector_lower, "brevo_official")

    def render(self, body_html: str, company_name: str = "",
               cta_url: str = None, cta_text: str = None,
               unsubscribe_url: str = None, sector: str = "",
               headline: str = "") -> str:
        """İçeriği en uygun şablona yerleştir."""
        template_id = self.get_best_template(sector) if sector else self._active_template
        template = TEMPLATES.get(template_id, TEMPLATES["fleet_corporate"])

        if not headline:
            headline = f"Slim vlootbeheer voor {company_name}" if company_name else "Slim vlootbeheer begint hier"

        try:
            # Brevo templates use different placeholder sets
            if template_id == "brevo_product":
                # Product template only has unsubscribe_url and cta_url
                format_kwargs = {
                    "unsubscribe_url": unsubscribe_url or DEFAULT_UNSUB_URL,
                    "cta_url": cta_url or DEFAULT_CTA_URL,
                }
            elif template_id == "brevo_official":
                # Official template has headline, body, cta, unsubscribe
                format_kwargs = {
                    "body_content": body_html,
                    "company_name": company_name or "Geachte heer/mevrouw",
                    "cta_url": cta_url or DEFAULT_CTA_URL,
                    "cta_text": cta_text or DEFAULT_CTA_TEXT,
                    "unsubscribe_url": unsubscribe_url or DEFAULT_UNSUB_URL,
                    "headline": headline,
                }
            else:
                # Legacy templates use all placeholders including images
                format_kwargs = {
                    "body_content": body_html,
                    "company_name": company_name or "Geachte heer/mevrouw",
                    "cta_url": cta_url or DEFAULT_CTA_URL,
                    "cta_text": cta_text or DEFAULT_CTA_TEXT,
                    "unsubscribe_url": unsubscribe_url or DEFAULT_UNSUB_URL,
                    "headline": headline,
                    "logo_url": IMAGES["logo"],
                    "img_fmc130": IMAGES["fmc130"],
                    "img_fmb920": IMAGES["fmb920"],
                    "img_fmb140": IMAGES["fmb140"],
                    "img_fmc650": IMAGES["fmc650"],
                }
            return template["html"].format(**format_kwargs)
        except KeyError as e:
            log.warning(f"Template render hatası ({template_id}): {e}")
            minimal = TEMPLATES["fleet_minimal"]
            return minimal["html"].format(
                body_content=body_html,
                company_name=company_name or "Geachte heer/mevrouw",
                cta_url=cta_url or DEFAULT_CTA_URL,
                cta_text=cta_text or DEFAULT_CTA_TEXT,
                unsubscribe_url=unsubscribe_url or DEFAULT_UNSUB_URL,
                logo_url=IMAGES["logo"],
                img_fmc130=IMAGES["fmc130"],
                img_fmb920=IMAGES["fmb920"],
                img_fmb140=IMAGES["fmb140"],
                img_fmc650=IMAGES["fmc650"],
                headline=headline,
            )

    def preview(self, template_id: str, sample_content: str = None) -> str:
        """Şablon önizlemesi oluştur."""
        template = TEMPLATES.get(template_id)
        if not template:
            return "<p>Template bulunamadı</p>"

        content = sample_content or (
            '<p style="margin:0 0 16px;font-size:15px;color:#333;line-height:1.7;">'
            "Beste heer/mevrouw,</p>"
            '<p style="margin:0 0 16px;font-size:15px;color:#333;line-height:1.7;">'
            "Wist u dat bedrijven met GPS fleet tracking gemiddeld "
            '<strong style="color:#CC0000;">23% brandstofbesparing</strong> realiseren?</p>'
            '<p style="margin:0 0 16px;font-size:15px;color:#333;line-height:1.7;">'
            "FleetTrack Holland biedt u een complete oplossing voor "
            "voertuigbeheer, routeoptimalisatie en real-time tracking.</p>"
            '<p style="margin:0;font-size:15px;color:#333;line-height:1.7;">'
            "Met vriendelijke groet,<br>"
            '<strong>FleetTrack Holland Team</strong><br>'
            '<span style="color:#888;font-size:13px;">sales@fleettrackholland.nl</span></p>'
        )

        try:
            return template["html"].format(
                body_content=content,
                company_name="Uw Bedrijf",
                cta_url=DEFAULT_CTA_URL,
                cta_text=DEFAULT_CTA_TEXT,
                unsubscribe_url=DEFAULT_UNSUB_URL,
                logo_url=IMAGES["logo"],
                img_fmc130=IMAGES["fmc130"],
                img_fmb920=IMAGES["fmb920"],
                img_fmb140=IMAGES["fmb140"],
                img_fmc650=IMAGES["fmc650"],
                headline="Bespaar tot 25% op uw vlootkosten",
            )
        except KeyError:
            return "<p>Preview rendering mislukt</p>"

    def ping(self) -> bool:
        return True
