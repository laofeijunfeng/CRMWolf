"""
测试价格计算逻辑
"""
from app.services.pricing import pricing_service, PricingCalculationError, LicenseType


def test_pricing_calculations():
    """测试各种价格计算场景"""
    
    print("=" * 80)
    print("价格计算逻辑测试")
    print("=" * 80)
    
    test_cases = [
        {
            "name": "订阅制 - 1年",
            "total_amount": 120000,
            "user_count": 10,
            "license_type": LicenseType.SUBSCRIPTION,
            "subscription_years": 1,
            "expected": "12000.00"
        },
        {
            "name": "订阅制 - 3年",
            "total_amount": 300000,
            "user_count": 50,
            "license_type": LicenseType.SUBSCRIPTION,
            "subscription_years": 3,
            "expected": "2000.00"
        },
        {
            "name": "买断制 - 标准5年折算",
            "total_amount": 250000,
            "user_count": 50,
            "license_type": LicenseType.PERPETUAL,
            "subscription_years": None,
            "expected": "1000.00"
        },
        {
            "name": "订阅制 - 小额项目",
            "total_amount": 5000,
            "user_count": 5,
            "license_type": LicenseType.SUBSCRIPTION,
            "subscription_years": 1,
            "expected": "1000.00"
        },
        {
            "name": "买断制 - 大型项目",
            "total_amount": 500000,
            "user_count": 100,
            "license_type": LicenseType.PERPETUAL,
            "subscription_years": None,
            "expected": "1000.00"
        }
    ]
    
    print("\n1. 正常计算测试:")
    print("-" * 80)
    
    passed = 0
    failed = 0
    
    for i, test_case in enumerate(test_cases, 1):
        try:
            result = pricing_service.calculate_unit_price(
                total_amount=test_case["total_amount"],
                user_count=test_case["user_count"],
                license_type=test_case["license_type"],
                subscription_years=test_case.get("subscription_years", 1)
            )
            
            result_str = str(result)
            status = "✓" if result_str == test_case["expected"] else "✗"
            
            if result_str == test_case["expected"]:
                passed += 1
            else:
                failed += 1
            
            print(f"{status} 测试 {i}: {test_case['name']}")
            print(f"  输入: 总金额={test_case['total_amount']}, 用户数={test_case['user_count']}")
            print(f"  授权模式: {test_case['license_type'].value}", end="")
            if test_case['subscription_years']:
                print(f", 年限={test_case['subscription_years']}")
            else:
                print()
            print(f"  期望结果: {test_case['expected']}")
            print(f"  实际结果: {result_str}")
            print()
            
        except Exception as e:
            failed += 1
            print(f"✗ 测试 {i}: {test_case['name']}")
            print(f"  异常: {str(e)}")
            print()
    
    print("\n2. 异常处理测试:")
    print("-" * 80)
    
    error_test_cases = [
        {
            "name": "用户数为0",
            "params": {
                "total_amount": 10000,
                "user_count": 0,
                "license_type": LicenseType.SUBSCRIPTION,
                "subscription_years": 1
            }
        },
        {
            "name": "用户数为负数",
            "params": {
                "total_amount": 10000,
                "user_count": -5,
                "license_type": LicenseType.SUBSCRIPTION,
                "subscription_years": 1
            }
        },
        {
            "name": "订阅年限为0",
            "params": {
                "total_amount": 10000,
                "user_count": 10,
                "license_type": LicenseType.SUBSCRIPTION,
                "subscription_years": 0
            }
        },
        {
            "name": "无效的授权模式",
            "params": {
                "total_amount": 10000,
                "user_count": 10,
                "license_type": "INVALID",
                "subscription_years": 1
            }
        }
    ]
    
    error_passed = 0
    error_failed = 0
    
    for i, test_case in enumerate(error_test_cases, 1):
        try:
            result = pricing_service.calculate_unit_price(**test_case["params"])
            error_failed += 1
            print(f"✗ 测试 {i}: {test_case['name']}")
            print(f"  预期抛出异常，但得到结果: {result}")
            print()
        except PricingCalculationError as e:
            error_passed += 1
            print(f"✓ 测试 {i}: {test_case['name']}")
            print(f"  正确抛出异常: {str(e)}")
            print()
        except Exception as e:
            error_failed += 1
            print(f"✗ 测试 {i}: {test_case['name']}")
            print(f"  抛出意外异常: {type(e).__name__}: {str(e)}")
            print()
    
    print("\n" + "=" * 80)
    print("测试结果汇总")
    print("=" * 80)
    print(f"正常计算测试: 通过 {passed}/{len(test_cases)}, 失败 {failed}/{len(test_cases)}")
    print(f"异常处理测试: 通过 {error_passed}/{len(error_test_cases)}, 失败 {error_failed}/{len(error_test_cases)}")
    
    total_passed = passed + error_passed
    total_failed = failed + error_failed
    total_tests = len(test_cases) + len(error_test_cases)
    
    print(f"总计: 通过 {total_passed}/{total_tests}, 失败 {total_failed}/{total_tests}")
    
    if total_failed == 0:
        print("\n🎉 所有测试通过！")
    else:
        print(f"\n⚠️  有 {total_failed} 个测试失败")
    
    print("=" * 80)


def test_validation():
    """测试输入验证"""
    print("\n" + "=" * 80)
    print("输入参数验证测试")
    print("=" * 80)
    
    test_cases = [
        {
            "name": "有效输入 - 订阅制",
            "params": {
                "total_amount": 10000,
                "user_count": 10,
                "license_type": LicenseType.SUBSCRIPTION,
                "subscription_years": 1
            },
            "expected_valid": True
        },
        {
            "name": "有效输入 - 买断制",
            "params": {
                "total_amount": 50000,
                "user_count": 50,
                "license_type": LicenseType.PERPETUAL,
                "subscription_years": None
            },
            "expected_valid": True
        },
        {
            "name": "无效输入 - 订阅制缺少年限",
            "params": {
                "total_amount": 10000,
                "user_count": 10,
                "license_type": LicenseType.SUBSCRIPTION,
                "subscription_years": None
            },
            "expected_valid": False
        },
        {
            "name": "无效输入 - 总金额为0",
            "params": {
                "total_amount": 0,
                "user_count": 10,
                "license_type": LicenseType.PERPETUAL,
                "subscription_years": None
            },
            "expected_valid": False
        }
    ]
    
    print()
    passed = 0
    failed = 0
    
    for test_case in test_cases:
        is_valid, error_msg = pricing_service.validate_pricing_input(**test_case["params"])
        
        if is_valid == test_case["expected_valid"]:
            passed += 1
            status = "✓"
        else:
            failed += 1
            status = "✗"
        
        print(f"{status} {test_case['name']}")
        print(f"  期望: {'有效' if test_case['expected_valid'] else '无效'}")
        print(f"  结果: {'有效' if is_valid else '无效'}")
        if error_msg:
            print(f"  错误信息: {error_msg}")
        print()
    
    print("=" * 80)


if __name__ == "__main__":
    test_pricing_calculations()
    test_validation()
