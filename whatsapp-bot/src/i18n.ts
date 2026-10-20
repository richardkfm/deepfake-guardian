/**
 * Bot UI messages (WhatsApp formatting: *bold*), mirroring the Telegram bot's
 * `i18n/*.json` keys. Falls back to English for unknown languages / keys.
 */

type Messages = Record<string, string>;

const en: Messages = {
  flagged_content: "⚠️ Flagged content ({reasons}). Admins: {mentions}",
  flagged_content_no_admins: "⚠️ Flagged content ({reasons}).",
  delete_failed:
    "⚠️ This message breaks the community guidelines ({reasons}) but I cannot delete it — please remove it and make me a group admin. Admins: {mentions}",
  delete_failed_no_admins:
    "⚠️ This message breaks the community guidelines ({reasons}) but I cannot delete it. An admin should remove it and make me a group admin.",

  warning_notice:
    "⚠️ A message was removed because it violated community guidelines ({reasons}). Please keep this space safe and respectful.",
  warning_admin_notification:
    "⚠️ Repeated violation by {mention} ({reasons}). Admins: {mentions}",
  warning_admin_notification_no_admins:
    "⚠️ Repeated violation ({reasons}). This is warning #{count} for this user.",
  warning_supervisor_escalation:
    "🚨 Persistent violations by {mention} ({reasons}) — {count} incidents recorded. Admins: {mentions} — please review and take action.",
  warning_supervisor_escalation_no_admins:
    "🚨 Persistent violations ({reasons}) — {count} incidents recorded. Please review and take action.",

  privacy_notice:
    "🔒 *Privacy Notice*\n\nDeepfake Guardian moderates content in this group to protect all members. Here is how your data is handled:\n\n• Messages are analysed for harmful content but *never stored*.\n• Only metadata (verdict, category scores) is logged — no message text.\n• Your user ID is stored as a one-way hash (never in plain text).\n• All data is automatically deleted after 30 days.\n• You can request deletion of your data at any time.\n\nSend /my_data to me in a private chat to see what is stored about you (GDPR Article 15).\nSend /delete_my_data to submit an erasure request (GDPR Article 17).",
  delete_my_data_submitted:
    "✅ Your data deletion request has been submitted (request ID: {request_id}). All stored data associated with your account will be erased within 30 days.",
  delete_my_data_already_pending:
    "ℹ️ A deletion request is already pending for your account (request ID: {request_id}). Your data will be erased within 30 days.",
  delete_my_data_error:
    "❌ Could not submit your deletion request. Please try again later or contact an admin.",
  my_data_private_only:
    "🔒 To protect your privacy, please send /my_data to me in a private chat.",
  my_data_summary:
    "🔒 *Your stored data*\n\nPseudonymous ID: {user_hash}…\n• Moderation events: {events}\n• Warning records: {warnings}\n• Deletion requests: {deletion_requests}\n\nNo message content is ever stored. Send /delete_my_data to request erasure.",
  my_data_error:
    "❌ Could not retrieve your data. Please try again later or contact an admin.",
};

const de: Messages = {
  flagged_content: "⚠️ Markierter Inhalt ({reasons}). Admins: {mentions}",
  flagged_content_no_admins: "⚠️ Markierter Inhalt ({reasons}).",
  delete_failed:
    "⚠️ Diese Nachricht verstößt gegen die Community-Richtlinien ({reasons}), aber ich kann sie nicht löschen – bitte entfernt sie und macht mich zum Gruppen-Admin. Admins: {mentions}",
  delete_failed_no_admins:
    "⚠️ Diese Nachricht verstößt gegen die Community-Richtlinien ({reasons}), aber ich kann sie nicht löschen. Ein Admin sollte sie entfernen und mich zum Gruppen-Admin machen.",

  warning_notice:
    "⚠️ Eine Nachricht wurde entfernt, da sie gegen die Community-Richtlinien verstößt ({reasons}). Bitte haltet diesen Raum sicher und respektvoll.",
  warning_admin_notification:
    "⚠️ Wiederholter Verstoß von {mention} ({reasons}). Admins: {mentions}",
  warning_admin_notification_no_admins:
    "⚠️ Wiederholter Verstoß ({reasons}). Dies ist Verwarnung Nr. {count} für diesen Nutzer.",
  warning_supervisor_escalation:
    "🚨 Anhaltende Verstöße von {mention} ({reasons}) – {count} Vorfälle dokumentiert. Admins: {mentions} – bitte überprüfen und handeln.",
  warning_supervisor_escalation_no_admins:
    "🚨 Anhaltende Verstöße ({reasons}) – {count} Vorfälle dokumentiert. Bitte überprüfen und handeln.",

  privacy_notice:
    "🔒 *Datenschutzhinweis*\n\nDeepfake Guardian moderiert Inhalte in dieser Gruppe, um alle Mitglieder zu schützen. So werden deine Daten verarbeitet:\n\n• Nachrichten werden auf schädliche Inhalte analysiert, aber *niemals gespeichert*.\n• Nur Metadaten (Urteil, Kategorie-Scores) werden protokolliert – kein Nachrichtentext.\n• Deine Nutzer-ID wird als Einweg-Hash gespeichert (niemals im Klartext).\n• Alle Daten werden nach 30 Tagen automatisch gelöscht.\n• Du kannst jederzeit die Löschung deiner Daten beantragen.\n\nSende mir /my_data im privaten Chat, um zu sehen, was über dich gespeichert ist (DSGVO Art. 15).\nSende /delete_my_data, um einen Löschantrag einzureichen (DSGVO Art. 17).",
  delete_my_data_submitted:
    "✅ Dein Löschantrag wurde eingereicht (Anfrage-ID: {request_id}). Alle gespeicherten Daten deines Kontos werden innerhalb von 30 Tagen gelöscht.",
  delete_my_data_already_pending:
    "ℹ️ Für dein Konto ist bereits ein Löschantrag ausstehend (Anfrage-ID: {request_id}). Deine Daten werden innerhalb von 30 Tagen gelöscht.",
  delete_my_data_error:
    "❌ Dein Löschantrag konnte nicht eingereicht werden. Bitte versuche es später erneut oder wende dich an einen Admin.",
  my_data_private_only:
    "🔒 Zum Schutz deiner Privatsphäre sende mir /my_data bitte in einem privaten Chat.",
  my_data_summary:
    "🔒 *Deine gespeicherten Daten*\n\nPseudonyme ID: {user_hash}…\n• Moderationsereignisse: {events}\n• Verwarnungseinträge: {warnings}\n• Löschanträge: {deletion_requests}\n\nNachrichteninhalte werden niemals gespeichert. Sende /delete_my_data, um die Löschung zu beantragen.",
  my_data_error:
    "❌ Deine Daten konnten nicht abgerufen werden. Bitte versuche es später erneut oder wende dich an einen Admin.",
};

export const MESSAGES: Readonly<Record<string, Messages>> = { en, de };

const FALLBACK_LANG = "en";

/** Return a localised message with `{placeholder}`s filled in. */
export function getMessage(
  key: string,
  lang: string,
  params: Record<string, string | number> = {}
): string {
  const template = MESSAGES[lang]?.[key] ?? MESSAGES[FALLBACK_LANG][key];
  if (template === undefined) return key;
  return template.replace(/\{(\w+)\}/g, (match, name: string) =>
    name in params ? String(params[name]) : match
  );
}
