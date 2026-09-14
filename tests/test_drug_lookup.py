"""drug_lookup 工具测试：命中 / 子串命中 / 未命中。"""
from app.tools.drug_lookup import drug_lookup


def test_exact_hit():
    out = drug_lookup.invoke({"drug_name": "布洛芬"})
    assert "布洛芬" in out
    assert "适应症" in out and "禁忌" in out


def test_substring_hit():
    out = drug_lookup.invoke({"drug_name": "请问对乙酰氨基酚一次吃多少？"})
    assert "对乙酰氨基酚" in out
    assert "用法用量" in out


def test_miss():
    out = drug_lookup.invoke({"drug_name": "青霉素V钾片"})
    assert "未收录" in out
    assert "布洛芬" in out  # 提示可用药品清单


def test_empty_input():
    out = drug_lookup.invoke({"drug_name": ""})
    assert "未收录" in out
