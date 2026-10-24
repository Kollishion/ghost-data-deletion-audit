"""Rules-only request intent classifier.

The public API accepts request text only. It never receives row metadata.
"""

from __future__ import annotations

import re
import unicodedata


AUTHORIZED = "AUTHORIZED"
NOT_APPLICABLE = "NOT_APPLICABLE"
UNCERTAIN = "UNCERTAIN"


def _normalize(text: str) -> str:
    value = unicodedata.normalize("NFKC", text or "").casefold()
    return re.sub(r"\s+", " ", value).strip()


DELETION_PATTERNS = (
    # English
    r"\b(?:delete|delet(?:ion|ed|ing)|erase|erasure|remove|removal|wipe|purge|close|shut down|terminate|cancel)\b[^.!?;]{0,100}\b(?:my|the|this|associated|personal|account|profile|data|information|records?|copies|details)\b",
    r"\b(?:my|the|this|personal|account|profile|data|information|records?|copies|details)\b[^.!?;]{0,60}\b(?:delete|erase|remove|wipe|purge|close|shut down|terminate|cancel)(?:d|ing)?\b",
    r"\b(?:request for|requesting)\b[^.!?;]{0,50}\b(?:permanent|permanently)?\s*(?:account )?deletion\b",
    r"\b(?:delete|remove|erase)\b[^.!?;]{0,55}\b(?:export file|download link|search result|index result)\b",
    r"\b(?:before deleting|before deletion|while deleting)\b.{0,80}\b(?:check|ensure|confirm|review)\b",
    r"\bconfirm\b[^.!?;]{0,80}\b(?:profile|account)\s+(?:is|will be)\s+gone\b",
    r"\bprofile\s+(?:is|should be)\s+gone\b.{0,80}\b(?:cannot|can no longer|can't)\s+identify me\b",
    r"\b(?:i(?:'d| would) like|i want|please|i request|i(?:'m| am))\b.{0,60}\b(?:account|data|profile)\b.{0,50}\b(?:closed|deleted|erased|removed)\b",
    # Portuguese, Spanish, French
    r"\b(?:apagar|apague|apagar|excluir|exclua|deletar|eliminar|elimine|remover|remova|encerrar|fechar|cancele|cancelar)\b.{0,90}\b(?:conta|perfil|dados?|informações|informacoes|registros?|cópias|copias|pessoais)\b",
    r"\b(?:supprimer|supprimez|effacer|effacez|radier|résilier|resilier|fermer|clôturer|cloturer)\b.{0,90}\b(?:compte|profil|données|donnees|informations|dossier|copies|personnelles)\b",
    r"\b(?:borrar|eliminar|suprimir|cerrar|cierre|supresión|supresion)\b.{0,90}\b(?:mi|la|el|esta)?\s*(?:cuenta|perfil|datos?|información|informacion|registros?|copias)\b",
    r"\b(?:suppression|effacement|fermeture)\b.{0,80}\b(?:de mon|du|mon|ma|mes)?\s*(?:compte|profil|données|donnees|informations)\b",
    r"\b(?:exclusão|exclusao|eliminação|eliminacao|supressão|supressao)\b.{0,80}\b(?:da|de|do|minha|minha)?\s*(?:conta|perfil|dados|informações|informacoes)\b",
    r"\b(?:eliminación|eliminacion|supresión|supresion)\b.{0,80}\b(?:de la|de mi|del|mi)?\s*(?:cuenta|perfil|datos|información|informacion)\b",
    r"\b(?:cuenta|perfil|datos?|información|informacion|registros?|copias)\b.{0,70}\b(?:eliminar|borra|borrar|suprimir|cerrar)\b",
    # Japanese and Korean
    r"(?:アカウント|個人データ|個人情報|データ).{0,20}(?:削除|消去|抹消|解約|閉鎖)",
    r"(?:削除|消去|抹消|解約|閉鎖).{0,20}(?:アカウント|個人データ|個人情報|データ)",
    r"(?:계정|개인정보|개인 데이터|데이터).{0,20}(?:삭제|제거|탈퇴|해지)",
    r"(?:삭제|제거|탈퇴|해지).{0,20}(?:계정|개인정보|개인 데이터|데이터)",
)

NEGATED_DELETION_PATTERNS = (
    r"\b(?:do not|don't|dont|never|not)\b.{0,50}\b(?:delete|erase|remove|wipe|purge|close|cancel)\b",
    r"\b(?:keep|retain|leave)\b.{0,40}\b(?:my|the)?\s*(?:account|profile|data)\b",
    r"\b(?:not|never)\b.{0,45}\b(?:asking|requesting|want)\b.{0,45}\b(?:delete|erase|remove)\b",
    r"\b(?:não|nao)\b.{0,35}\b(?:apague|apagar|excluir|delete|remover|eliminar)\b",
    r"\b(?:mant(?:er|enha)|preservar)\b.{0,45}\b(?:conta|perfil|dados)\b",
    r"\b(?:não|nao)\b.{0,35}\b(?:quero|solicito|peço|peco)\b.{0,30}\b(?:excluir|apagar|deletar|remover)\b",
    r"\bno\b.{0,35}\b(?:borres|borrar|elimines|eliminar|suprimir)\b",
    r"\b(?:mantener|conservar)\b.{0,45}\b(?:mi|la)?\s*(?:cuenta|perfil|datos)\b",
    r"\bne\b.{0,30}\b(?:supprimez?|effacez?|résiliez?|resiliez?)\b.{0,20}\bpas\b",
    r"\bje ne demande pas\b.{0,50}\b(?:suppression|effacement|résiliation|resiliation)\b",
    r"\b(?:garder|conserver)\b.{0,45}\b(?:mon|ma|le|la)?\s*(?:compte|profil|données|donnees)\b",
    r"(?:削除|消去|解約).{0,8}(?:しないで|しません|しない|不要)",
    r"(?:削除|消去|解約).{0,16}(?:求めていません|希望していません|依頼していません)",
    r"(?:削除|消去|解約).{0,12}(?:求めて|希望して|依頼して).{0,8}いません",
    r"(?:アカウント|データ).{0,12}(?:残して|維持して|そのまま)",
    r"(?:삭제|제거|해지).{0,8}(?:하지 마|하지말|하지 않|하지않)",
    r"(?:삭제|제거|해지).{0,16}(?:요청이 아니라|원하지 않|요청하지 않)",
    r"(?:계정|데이터).{0,12}(?:유지|남겨|그대로)",
)

NON_DELETION_PATTERNS = (
    # Explicit access, correction, export, marketing opt-out, login help,
    # and email/phone change requests. Checked only after deletion/refusal.
    r"\b(?:access|view|see|copy of|download|export|send me|provide me)\b.{0,80}\b(?:my data|my information|my records|personal data|account data)\b",
    r"\b(?:correct|correction|fix|update|change)\b.{0,70}\b(?:my|the)?\s*(?:name|address|profile|record|data|details|information)\b",
    r"\b(?:correct|correction|fix|update|change)\b.{0,60}\b(?:it|without removing|without deleting|without erasing)\b",
    r"\b(?:export|download|portability)\b.{0,70}\b(?:my|the)?\s*(?:data|records|information|account)\b",
    r"\b(?:opt out|opt-out|unsubscribe|stop|disable)\b.{0,60}\b(?:marketing|advertising|promotional|offers|emails)\b",
    r"\bremove me from\b.{0,45}\b(?:marketing lists|marketing|advertising|promotional lists)\b",
    r"\b(?:cannot|can't|unable to|help me|assist me)\b.{0,45}\b(?:log in|login|sign in|password|access my account)\b",
    r"\b(?:change|update|replace)\b.{0,50}\b(?:email|e-mail|phone|telephone|mobile number)\b",
    r"\b(?:acessar|consultar|ver|obter|baixar|exportar)\b.{0,70}\b(?:meus dados|minhas informações|meus registros)\b",
    r"\b(?:corrigir|atualizar|alterar)\b.{0,70}\b(?:nome|endereço|endereco|perfil|dados|telefone|email)\b",
    r"\b(?:cancelar|recusar|desativar|parar)\b.{0,55}\b(?:marketing|publicidade|promoções|promocoes|emails promocionais)\b",
    r"\b(?:parar|cancelar|recusar|desativar)\b.{0,55}\b(?:marketing|publicidade|promoções|promocoes)\b",
    r"\b(?:pare|parar|cancele|cancelar)\b.{0,45}\b(?:de enviar|de receber)\b.{0,40}\b(?:marketing|publicidade|promoções|promocoes)\b",
    r"\b(?:cambiar|actualizar|corregir)\b.{0,65}\b(?:correo|email|teléfono|telefono|número|numero|nombre|dirección|direccion)\b",
    r"\b(?:acceso|acceder|consultar|exportar|descargar)\b.{0,70}\b(?:mis datos|mi información|mi informacion|mis registros)\b",
    r"\b(?:optar por no|cancelar|dejar de recibir|desactivar)\b.{0,60}\b(?:marketing|publicidad|promociones)\b",
    r"\b(?:accéder|acceder|consulter|télécharger|telecharger|exporter)\b.{0,70}\b(?:mes données|mes donnees|mon dossier|mes informations)\b",
    r"\b(?:corriger|modifier|mettre à jour|mettre a jour|changer)\b.{0,60}\b(?:mon|ma|mes)?\s*(?:adresse|nom|profil|données|donnees|email|téléphone|telephone)\b",
    r"\b(?:désabonner|desabonner|refuser|désactiver|desactiver)\b.{0,55}\b(?:marketing|publicité|publicite|promotions)\b",
    r"\b(?:arrêter|arreter|cesser|stopper)\b.{0,55}\b(?:les courriels|les emails|le marketing|la publicité|la publicite)\b",
    r"(?:データ|情報).{0,12}(?:開示|確認|取得|ダウンロード|エクスポート)",
    r"(?:修正|訂正|変更).{0,16}(?:住所|名前|メール|電話|プロフィール|情報)",
    r"(?:マーケティング|広告|宣伝).{0,12}(?:停止|解除|配信停止)",
    r"(?:ログイン|サインイン).{0,16}(?:できない|できません|助けて|支援)",
    r"(?:데이터|정보).{0,12}(?:열람|조회|다운로드|내보내기)",
    r"(?:수정|변경|정정).{0,16}(?:주소|이름|이메일|전화|프로필|정보)",
    r"(?:마케팅|광고|홍보).{0,12}(?:수신 거부|중단|해지)",
    r"(?:로그인|접속).{0,16}(?:도와|문제|안 돼|안돼)",
)


def classify_request(request_text: str) -> str:
    """Return AUTHORIZED, NOT_APPLICABLE, or UNCERTAIN from text alone."""
    text = _normalize(request_text)
    positive = any(re.search(p, text, re.I) for p in DELETION_PATTERNS)
    negated = any(re.search(p, text, re.I) for p in NEGATED_DELETION_PATTERNS)
    if positive and not negated:
        return AUTHORIZED
    if negated:
        return NOT_APPLICABLE
    # The second pass is intentionally restricted to explicit non-deletion
    # actions. It cannot cancel a clear deletion request.
    if any(re.search(p, text, re.I) for p in NON_DELETION_PATTERNS):
        return NOT_APPLICABLE
    return UNCERTAIN
