package ru.slavitsa.sverkapro.core;

import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.regex.Pattern;

public final class TableData {
    private static final Pattern NON_HEADER = Pattern.compile("[^a-zа-яё0-9]+");

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
        this.columns = Collections.unmodifiableMap(detectColumns(headers));
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
        return NON_HEADER.matcher(normalizeText(value)).replaceAll("");
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
}
