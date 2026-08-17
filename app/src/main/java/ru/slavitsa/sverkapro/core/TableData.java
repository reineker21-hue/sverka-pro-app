package ru.slavitsa.sverkapro.core;

import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.regex.Pattern;

public final class TableData {
    private static final Pattern DATE_IN_TEXT = Pattern.compile(
            "(?<!\\d)(?:\\d{1,2}[./\\-]\\d{1,2}[./\\-]\\d{2,4}|\\d{4}[./\\-]\\d{1,2}[./\\-]\\d{1,2})(?!\\d)");
    private static final List<String> DOCUMENT_HINTS = List.of(
            "оплата", "отгрузка", "поступление", "реализация", "корректировка",
            "возврат", "накладная", "счет", "счёт", "акт", "упд", "платеж", "платёж");

    private static final Map<String, List<String>> ALIASES;
    static {
        Map<String, List<String>> aliases = new LinkedHashMap<>();
        aliases.put("date", List.of("дата", "дата операции", "дата документа", "датадокумента", "date", "период"));
        aliases.put("document", List.of(
                "документ", "номер документа", "номердокумента", "№ документа", "номер",
                "док", "основание", "счет фактура", "счет-фактура", "накладная", "акт",
                "содержание", "операция", "вид документа", "тип документа",
                "представление документа", "документ основание", "назначение", "расшифровка",
                "наименование операции, документ"));
        aliases.put("debit", List.of("дебет", "дебет оборот", "оборот дебет", "дебетовый оборот", "приход"));
        aliases.put("credit", List.of("кредит", "кредит оборот", "оборот кредит", "кредитовый оборот", "расход"));
        aliases.put("balance", List.of("сальдо", "остаток", "баланс", "конечное сальдо", "конечный остаток"));
        aliases.put("counterparty", List.of("контрагент", "поставщик", "покупатель", "организация", "наименование", "партнер"));
        ALIASES = Collections.unmodifiableMap(aliases);
    }

    public final String sourceName;
    public final String sheetName;
    public final List<String> headers;
    public final List<Map<String, Object>> rows;
    public final Map<String, String> columns;

    private TableData(String sourceName, String sheetName, List<String> headers,
                      List<Map<String, Object>> rows) {
        this.sourceName = sourceName;
        this.sheetName = sheetName;
        this.headers = Collections.unmodifiableList(headers);
        this.rows = Collections.unmodifiableList(rows);
        this.columns = Collections.unmodifiableMap(detectColumns(headers, rows));
    }

    public static TableData fromMatrix(String sourceName, String sheetName, List<List<Object>> matrix) {
        if (matrix == null || matrix.isEmpty()) {
            throw new IllegalArgumentException("В файле не найден непустой лист с таблицей.");
        }
        int headerIndex = chooseHeaderRow(matrix);
        List<String> headers = makeHeaders(matrix.get(headerIndex));
        List<Map<String, Object>> rows = new ArrayList<>();
        for (int rowIndex = headerIndex + 1; rowIndex < matrix.size(); rowIndex++) {
            List<Object> raw = matrix.get(rowIndex);
            if (!hasValues(raw)) continue;
            Map<String, Object> row = new LinkedHashMap<>();
            for (int col = 0; col < headers.size(); col++) {
                row.put(headers.get(col), col < raw.size() ? raw.get(col) : null);
            }
            rows.add(row);
        }
        if (rows.isEmpty()) {
            throw new IllegalArgumentException("После заголовка таблицы не найдено строк данных.");
        }
        return new TableData(sourceName, sheetName, headers, rows);
    }

    public static Map<String, List<String>> aliases() {
        return ALIASES;
    }

    public static String normalizeText(Object value) {
        if (value == null) return "";
        return value.toString().trim().toLowerCase(Locale.ROOT).replace('ё', 'е').replaceAll("\\s+", " ");
    }

    public static String normalizeHeader(Object value) {
        String text = normalizeText(value);
        StringBuilder normalized = new StringBuilder(text.length());
        for (int index = 0; index < text.length(); index++) {
            char character = text.charAt(index);
            if (Character.isLetterOrDigit(character)) normalized.append(character);
        }
        return normalized.toString();
    }

    private static int chooseHeaderRow(List<List<Object>> matrix) {
        int bestIndex = 0;
        int bestScore = Integer.MIN_VALUE;
        int limit = Math.min(matrix.size(), 40);
        for (int index = 0; index < limit; index++) {
            List<Object> row = matrix.get(index);
            int nonEmpty = 0;
            for (Object value : row) if (value != null && !value.toString().trim().isEmpty()) nonEmpty++;
            if (nonEmpty == 0) continue;
            List<String> candidates = makeHeaders(row);
            int recognized = 0;
            Map<String, String> detected = detectColumns(candidates);
            for (String value : detected.values()) if (value != null) recognized++;
            int score = recognized * 100 + Math.min(nonEmpty, 30);
            if (score > bestScore) {
                bestScore = score;
                bestIndex = index;
            }
        }
        return bestIndex;
    }

    private static boolean hasValues(List<Object> row) {
        if (row == null) return false;
        for (Object value : row) {
            if (value != null && !value.toString().trim().isEmpty()) return true;
        }
        return false;
    }

    private static List<String> makeHeaders(List<Object> raw) {
        List<String> headers = new ArrayList<>();
        Map<String, Integer> used = new LinkedHashMap<>();
        int size = raw == null ? 0 : raw.size();
        for (int index = 0; index < size; index++) {
            Object value = raw.get(index);
            String name = value == null ? "" : value.toString().trim();
            if (name.isEmpty()) name = "Колонка " + (index + 1);
            int count = used.getOrDefault(name, 0) + 1;
            used.put(name, count);
            headers.add(count == 1 ? name : name + "_" + count);
        }
        return headers;
    }

    private static Map<String, String> detectColumns(List<String> headers) {
        Map<String, String> columns = new LinkedHashMap<>();
        for (Map.Entry<String, List<String>> entry : ALIASES.entrySet()) {
            String best = null;
            int bestScore = 0;
            for (String header : headers) {
                String normalized = normalizeHeader(header);
                for (String aliasValue : entry.getValue()) {
                    String alias = normalizeHeader(aliasValue);
                    int score = normalized.equals(alias) ? 100
                            : alias.length() > 0 && normalized.contains(alias) ? 70
                            : normalized.length() > 0 && alias.contains(normalized) ? 50 : 0;
                    if (score > bestScore) {
                        bestScore = score;
                        best = header;
                    }
                }
            }
            columns.put(entry.getKey(), best);
        }
        return columns;
    }

    private static Map<String, String> detectColumns(List<String> headers, List<Map<String, Object>> rows) {
        Map<String, String> columns = detectColumns(headers);
        if (columns.get("debit") != null && columns.get("credit") != null
                && columns.get("document") != null) return columns;

        List<ColumnProfile> profiles = profileColumns(headers, rows);
        inferMoneyColumns(columns, profiles);
        if (columns.get("document") == null) {
            ColumnProfile document = profiles.stream()
                    .filter(profile -> !profile.header.equals(columns.get("debit"))
                            && !profile.header.equals(columns.get("credit")))
                    .max((left, right) -> Integer.compare(left.documentScore(), right.documentScore()))
                    .orElse(null);
            if (document != null && document.documentScore() > 0) columns.put("document", document.header);
        }
        if (columns.get("date") == null) {
            ColumnProfile date = profiles.stream()
                    .filter(profile -> !profile.header.equals(columns.get("debit"))
                            && !profile.header.equals(columns.get("credit")))
                    .max((left, right) -> Integer.compare(left.dateCells, right.dateCells))
                    .orElse(null);
            if (date != null && date.dateCells > 0) columns.put("date", date.header);
        }
        return columns;
    }

    private static List<ColumnProfile> profileColumns(List<String> headers, List<Map<String, Object>> rows) {
        List<ColumnProfile> profiles = new ArrayList<>();
        for (int index = 0; index < headers.size(); index++) {
            String header = headers.get(index);
            ColumnProfile profile = new ColumnProfile(index, header);
            Double previous = null;
            int sequentialSteps = 0;
            for (Map<String, Object> row : rows) {
                Object value = row.get(header);
                if (value == null || value.toString().trim().isEmpty()) continue;
                Double numeric = numericValue(value);
                if (numeric != null) {
                    profile.numericCells++;
                    if (value instanceof Number) profile.numberObjects++;
                    if (Math.abs(numeric - Math.rint(numeric)) > 0.0000001) profile.decimalCells++;
                    profile.maxAbsolute = Math.max(profile.maxAbsolute, Math.abs(numeric));
                    if (previous != null && Math.abs(numeric - previous - 1.0) < 0.0000001) sequentialSteps++;
                    previous = numeric;
                }
                String text = normalizeText(value);
                if (DATE_IN_TEXT.matcher(text).find()) profile.dateCells++;
                for (String hint : DOCUMENT_HINTS) {
                    if (text.contains(hint)) {
                        profile.documentHints++;
                        break;
                    }
                }
            }
            profile.sequenceLike = profile.numericCells >= 5
                    && sequentialSteps >= Math.max(3, (profile.numericCells - 1) * 3 / 4);
            profiles.add(profile);
        }
        return profiles;
    }

    private static void inferMoneyColumns(Map<String, String> columns, List<ColumnProfile> profiles) {
        String debit = columns.get("debit");
        String credit = columns.get("credit");
        if (debit != null && credit != null) return;

        if (debit != null || credit != null) {
            ColumnProfile known = findProfile(profiles, debit != null ? debit : credit);
            ColumnProfile neighbor = bestMoneyNeighbor(profiles, known);
            if (neighbor != null) columns.put(debit == null ? "debit" : "credit", neighbor.header);
            return;
        }

        ColumnProfile bestLeft = null;
        ColumnProfile bestRight = null;
        int bestScore = Integer.MIN_VALUE;
        for (int left = 0; left < profiles.size(); left++) {
            for (int right = left + 1; right < profiles.size() && right <= left + 2; right++) {
                ColumnProfile a = profiles.get(left);
                ColumnProfile b = profiles.get(right);
                if (a.moneyScore() <= 0 && b.moneyScore() <= 0) continue;
                int score = a.moneyScore() + b.moneyScore() + (right == left + 1 ? 40 : 0);
                if (score > bestScore) {
                    bestScore = score;
                    bestLeft = a;
                    bestRight = b;
                }
            }
        }
        if (bestLeft != null) {
            columns.put("debit", bestLeft.header);
            columns.put("credit", bestRight.header);
            return;
        }

        ColumnProfile single = profiles.stream()
                .max((left, right) -> Integer.compare(left.moneyScore(), right.moneyScore())).orElse(null);
        if (single != null && single.moneyScore() > 0) columns.put("debit", single.header);
    }

    private static ColumnProfile bestMoneyNeighbor(List<ColumnProfile> profiles, ColumnProfile known) {
        if (known == null) return null;
        ColumnProfile best = null;
        int bestScore = Integer.MIN_VALUE;
        for (ColumnProfile profile : profiles) {
            int distance = Math.abs(profile.index - known.index);
            if (distance == 0 || distance > 2) continue;
            int score = profile.moneyScore() + (distance == 1 ? 40 : 0);
            if (score > bestScore) {
                best = profile;
                bestScore = score;
            }
        }
        return bestScore > 0 ? best : null;
    }

    private static ColumnProfile findProfile(List<ColumnProfile> profiles, String header) {
        if (header == null) return null;
        for (ColumnProfile profile : profiles) if (profile.header.equals(header)) return profile;
        return null;
    }

    private static Double numericValue(Object value) {
        if (value instanceof Number number) return number.doubleValue();
        String text = value == null ? "" : value.toString().trim()
                .replace("\u00A0", "").replace(" ", "").replace(',', '.');
        if (text.isEmpty()) return null;
        if (text.startsWith("(") && text.endsWith(")")) text = "-" + text.substring(1, text.length() - 1);
        try { return Double.parseDouble(text); } catch (NumberFormatException ignored) { return null; }
    }

    private static final class ColumnProfile {
        final int index;
        final String header;
        int numericCells;
        int numberObjects;
        int decimalCells;
        int dateCells;
        int documentHints;
        double maxAbsolute;
        boolean sequenceLike;

        ColumnProfile(int index, String header) {
            this.index = index;
            this.header = header;
        }

        int moneyScore() {
            if (numericCells == 0 || sequenceLike) return 0;
            int score = numericCells * 3 + numberObjects * 4 + decimalCells * 6;
            if (maxAbsolute >= 100.0) score += 25;
            return score;
        }

        int documentScore() {
            return documentHints * 20 + dateCells * 4;
        }
    }
}
